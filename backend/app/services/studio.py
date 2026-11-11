from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
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

    # nk flow slot titles (see nk_flow.py: find_slots / _titled_default).
    FLOW_TITLES = {
        "6": "NK prompt",
        "7": "NK negative",
        "3": "NK seed",
        "5": "NK size",
        "9": "NK output",
        "20": "NK lora",
    }
    FLOW_PROMPT = "%quality%, %artist%, safe, %char%, %scene%"
    FLOW_RE = re.compile(r"^[A-Za-z0-9_\-\uac00-\ud7a3.]{1,60}$")
    NON_SDXL_TOKENS = (
        "hunyuan",
        "sam3",
        "svd",
        "flux",
        "sd3",
        "anima",
        "acestep",
        "ace_step",
    )

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
    def flow_dir(self) -> Path:
        return self.kit_path / "workflows"

    def policy_agreed(self) -> bool:
        """nk asks for the use-policy consent once; the marker file records it."""
        marker = self.kit_path / ".nk_agreed"
        try:
            return marker.read_text(encoding="utf-8").split()[0] == "1"
        except Exception:
            return False

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
        if self._process is not None and self._process.poll() is None:
            return True
        # A studio that was started earlier (or by hand) keeps serving even if
        # this backend does not own the process.
        return self._port_open(self.port)

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
                # Something else already listens on that port (a studio that is
                # already running, maybe started by hand) - reuse it.
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

    # ------------------------------------------------------- model workflows
    def list_model_flows(self) -> list[dict[str, Any]]:
        """The generated per-model drawing workflows (the studio model list)."""
        if not self.flow_dir.is_dir():
            return []
        items: list[dict[str, Any]] = []
        for path in sorted(self.flow_dir.glob("*.json")):
            if path.stem.endswith("_final"):
                continue
            try:
                graph = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            model = ""
            for node in graph.values():
                if not isinstance(node, dict):
                    continue
                if node.get("class_type") == "CheckpointLoaderSimple":
                    model = str((node.get("inputs") or {}).get("ckpt_name") or "")
                    break
            if not model:
                continue
            steps = cfg = 0.0
            for node in graph.values():
                if not isinstance(node, dict):
                    continue
                if node.get("class_type") == "KSampler":
                    inputs = node.get("inputs") or {}
                    steps = int(inputs.get("steps") or 0)
                    cfg = float(inputs.get("cfg") or 0.0)
                    break
            items.append(
                {
                    "name": path.stem,
                    "model": model,
                    "steps": steps,
                    "cfg": cfg,
                }
            )
        return items

    def refresh_model_flows(self) -> list[dict[str, Any]]:
        """Write one nk drawing workflow per installed SDXL checkpoint.

        nk can draw a solo cut with a user workflow and the studio already
        lists those in its "그림 워크플로" dropdown, so this turns that
        dropdown into a model picker without touching nk code.
        """
        if not self.installed:
            raise StudioError(
                f"nk 만화 제작기를 찾지 못했습니다: {self.kit_path}",
            )
        self.flow_dir.mkdir(parents=True, exist_ok=True)
        models = self._sdxl_checkpoints()
        values = self._recommended_values()
        lora = self._first_lora()
        written: list[dict[str, Any]] = []
        for model in models:
            steps, cfg = values.get(model, (30, 5.5))
            name = self._flow_name(model)
            if not self.FLOW_RE.match(name):
                continue
            graph = self._build_flow_graph(model, steps, cfg, lora, name)
            (self.flow_dir / f"{name}.json").write_text(
                json.dumps(graph, ensure_ascii=False, indent=1), encoding="utf-8"
            )
            written.append({"name": name, "model": model, "steps": steps, "cfg": cfg})
        return written

    def _sdxl_checkpoints(self) -> list[str]:
        try:
            with httpx.Client(timeout=30) as client:
                info = client.get(
                    f"{self.settings.comfyui.normalized_url}/object_info/CheckpointLoaderSimple"
                ).json()
            names = info["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0]
        except Exception:
            return []
        return [
            name
            for name in names
            if not any(token in name.lower() for token in self.NON_SDXL_TOKENS)
        ]

    def _recommended_values(self) -> dict[str, tuple[int, float]]:
        """Per model steps/cfg from PixelForge's own model notes."""
        from app.services.model_catalog import model_files

        values: dict[str, tuple[int, float]] = {}
        try:
            models = model_files(
                self.settings, "checkpoint", set(self._sdxl_checkpoints())
            )
        except Exception:
            return values
        for model in models:
            if model.recommended_steps and model.recommended_cfg:
                values[model.name] = (
                    int(model.recommended_steps),
                    float(model.recommended_cfg),
                )
        return values

    def _first_lora(self) -> str:
        loras = (
            Path(self.settings.comfyui.models_dir).expanduser() / "loras"
            if self.settings.comfyui.models_dir
            else Path()
        )
        if loras.is_dir():
            for path in sorted(loras.glob("*.safetensors")):
                return path.name
        return ""

    @staticmethod
    def _flow_name(model: str) -> str:
        base = re.sub(r"[^A-Za-z0-9_\-\uac00-\ud7a3.]", "_", Path(model).stem)
        return base[:60]

    def _build_flow_graph(
        self, model: str, steps: int, cfg: float, lora: str, name: str
    ) -> dict[str, Any]:
        clip = ["20", 1] if lora else ["4", 1]
        model_link = ["20", 0] if lora else ["4", 0]
        graph: dict[str, Any] = {
            "4": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": model},
                "_meta": {"title": "CheckpointLoaderSimple"},
            },
            "6": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": self.FLOW_PROMPT, "clip": clip},
                "_meta": {"title": self.FLOW_TITLES["6"]},
            },
            "7": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": "%negative%", "clip": clip},
                "_meta": {"title": self.FLOW_TITLES["7"]},
            },
            "5": {
                "class_type": "EmptyLatentImage",
                "inputs": {"width": 832, "height": 1216, "batch_size": 1},
                "_meta": {"title": self.FLOW_TITLES["5"]},
            },
            "3": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": 1,
                    "steps": int(steps),
                    "cfg": float(cfg),
                    "sampler_name": "euler",
                    "scheduler": "normal",
                    "denoise": 1.0,
                    "model": model_link,
                    "positive": ["6", 0],
                    "negative": ["7", 0],
                    "latent_image": ["5", 0],
                },
                "_meta": {"title": self.FLOW_TITLES["3"]},
            },
            "8": {
                "class_type": "VAEDecode",
                "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
                "_meta": {"title": "VAEDecode"},
            },
            "9": {
                "class_type": "SaveImage",
                "inputs": {"filename_prefix": f"nk/{name}", "images": ["8", 0]},
                "_meta": {"title": self.FLOW_TITLES["9"]},
            },
        }
        if lora:
            graph["20"] = {
                "class_type": "LoraLoader",
                "inputs": {
                    "model": ["4", 0],
                    "clip": ["4", 1],
                    "lora_name": lora,
                    "strength_model": 0.0,
                    "strength_clip": 0.0,
                },
                "_meta": {"title": self.FLOW_TITLES["20"]},
            }
        return graph

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
