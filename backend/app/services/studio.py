from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings
from app.services.errors import PixelForgeError

logger = logging.getLogger("pixelforge.studio")

# Paths inside the studio HTML that must point back through the proxy.
_HTML_REWRITES = (
    ('"/api/', '"/studio/api/'),
    ('"/img?', '"/studio/img?'),
    ('"/img"', '"/studio/img"'),
    ('href="/label"', 'href="/studio/label"'),
    ('href="/ab"', 'href="/studio/ab"'),
    ('href="/"', 'href="/studio/"'),
)

_FORWARD_HEADERS = (
    "x-nk-k",
    "x-nk",
    "content-type",
    "accept",
    "cookie",
    "user-agent",
)


class StudioError(PixelForgeError):
    code = "STUDIO_ERROR"
    status_code = 503


class StudioService:
    """Runs the nk comic studio (``nk ep web``) and proxies it into PixelForge.

    The studio is a standalone local-only web app, so it is started on its own
    port and reached through ``/studio/``. That keeps every nk behaviour
    (queue, logs, cut re-rendering, page assembly) exactly as it is while it
    lives inside the PixelForge UI.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self._process: subprocess.Popen[bytes] | None = None
        self._log_handle: Any = None
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ paths
    @property
    def kit_path(self) -> Path:
        configured = self.settings.studio.kit_path
        if configured:
            candidate = Path(configured).expanduser()
            if (candidate / "nk.py").is_file():
                return candidate
        home = os.environ.get("NK_HOME")
        if home:
            candidate = Path(home).expanduser()
            if (candidate / "nk.py").is_file():
                return candidate
        default = Path(r"C:\nk")
        return default

    @property
    def installed(self) -> bool:
        return (self.kit_path / "nk.py").is_file()

    @property
    def port(self) -> int:
        return int(self.settings.studio.port)

    def python_executable(self) -> str:
        configured = self.settings.studio.python
        if configured:
            path = Path(configured).expanduser()
            if path.is_file():
                return str(path)
        found = shutil.which("python")
        return found or sys.executable

    # ----------------------------------------------------------------- status
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def status(self) -> dict[str, Any]:
        return {
            "installed": self.installed,
            "kit_path": str(self.kit_path),
            "running": self.is_running(),
            "port": self.port,
            "url": "/studio/",
            "python": self.python_executable(),
        }

    # ------------------------------------------------------------------- run
    def _port_open(self, port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.6)
            return sock.connect_ex(("127.0.0.1", port)) == 0

    async def ensure_running(self) -> bool:
        """Start the studio server if it is not up yet."""
        async with self._lock:
            if self.is_running():
                return True
            if not self.installed:
                raise StudioError(
                    "nk 만화 제작기를 찾지 못했습니다. "
                    f"{self.kit_path} 에 nk.py 가 있는지 확인해 주세요 "
                    "(config/settings.yaml 의 studio.kit_path 로 경로를 지정할 수 있습니다).",
                    detail=f"kit_path={self.kit_path}",
                )
            if self._port_open(self.port):
                # Something else already listens on that port (maybe a studio
                # the user started by hand) - reuse it instead of failing.
                logger.info("Studio server already listening on port %s", self.port)
                return True

            log_path = self.settings.logs_dir / "nk-studio.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            self._log_handle = log_path.open("a", encoding="utf-8", errors="replace")
            self._log_handle.write(
                f"\n\n===== PixelForge: nk studio start "
                f"{time.strftime('%Y-%m-%d %H:%M:%S')} =====\n"
            )
            self._log_handle.flush()
            args = [
                self.python_executable(),
                "nk.py",
                "ep",
                "web",
                "--port",
                str(self.port),
                "--no-open",
                # The studio runs the queue in its own worker thread. Keeping
                # nk_remote.py off avoids an extra console window popping up.
                "--no-runner",
            ]
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
            self._process = subprocess.Popen(
                args,
                cwd=str(self.kit_path),
                stdout=self._log_handle,
                stderr=subprocess.STDOUT,
                env=env,
                creationflags=creationflags,
            )
            deadline = time.monotonic() + 40
            while time.monotonic() < deadline:
                if self._process.poll() is not None:
                    self._process = None
                    raise StudioError(
                        "nk 작업실을 시작하지 못했습니다. logs/nk-studio.log 를 확인해 주세요.",
                        detail=self._log_tail(),
                    )
                if self._port_open(self.port):
                    logger.info("nk studio listening on 127.0.0.1:%s", self.port)
                    return True
                await asyncio.sleep(0.5)
            raise StudioError(
                "nk 작업실이 시간 안에 시작되지 않았습니다. logs/nk-studio.log 를 확인해 주세요.",
                detail=self._log_tail(),
            )

    def _log_tail(self, limit: int = 40) -> str:
        path = self.settings.logs_dir / "nk-studio.log"
        if not path.exists():
            return ""
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-limit:])

    async def stop(self) -> None:
        process = self._process
        self._process = None
        if process is not None and process.poll() is None:
            with contextlib.suppress(Exception):
                process.terminate()
                process.wait(timeout=8)
        if self._log_handle is not None:
            with contextlib.suppress(Exception):
                self._log_handle.close()
            self._log_handle = None

    # ------------------------------------------------------------------ proxy
    @staticmethod
    def rewrite_html(text: str) -> str:
        for old, new in _HTML_REWRITES:
            text = text.replace(old, new)
        return text

    async def proxy(
        self,
        method: str,
        path: str,
        query: str = "",
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
    ) -> tuple[int, str, bytes]:
        """Forward a request to the studio server and return its response."""
        await self.ensure_running()
        url = f"http://127.0.0.1:{self.port}/{path.lstrip('/')}"
        if query:
            url = f"{url}?{query}"
        forward: dict[str, str] = {}
        for name, value in (headers or {}).items():
            if name.lower() in _FORWARD_HEADERS:
                forward[name] = value
        forward["Host"] = f"127.0.0.1:{self.port}"
        timeout = httpx.Timeout(180.0, connect=5.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            try:
                response = await client.request(
                    method.upper(), url, headers=forward, content=body
                )
            except httpx.HTTPError as exc:
                raise StudioError(
                    "nk 작업실에 연결하지 못했습니다.",
                    detail=str(exc),
                ) from exc
        content_type = response.headers.get("content-type", "application/octet-stream")
        payload = response.content
        if "text/html" in content_type:
            try:
                payload = self.rewrite_html(payload.decode("utf-8")).encode("utf-8")
            except UnicodeDecodeError:
                pass
        return response.status_code, content_type, payload
