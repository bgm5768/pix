from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import yaml

from app.config import PROJECT_ROOT, Settings
from app.services.comfy_client import ComfyClient
from app.services.errors import ComfyConnectionError

_MODEL_FOLDERS = [
    "checkpoints",
    "loras",
    "vae",
    "text_encoders",
    "clip",
    "clip_vision",
    "controlnet",
    "embeddings",
    "upscale_models",
    "style_models",
    "diffusion_models",
    "unet",
    "model_patches",
    "audio_encoders",
    "background_removal",
    "frame_interpolation",
    "geometry_estimation",
    "optical_flow",
    "detection",
    "gligen",
    "hypernetworks",
    "latent_upscale_models",
    "photomaker",
    "vae_approx",
    "classifiers",
    "configs",
]


@dataclass
class ComfyPaths:
    install_dir: Path
    main_path: Path
    python_path: Path
    models_dir: Path
    input_dir: Path
    output_dir: Path


class ComfyLauncher:
    """Starts the existing ComfyUI installation when its API is not already up."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._process: subprocess.Popen | None = None
        self._log_handle = None
        self._started_by_us = False
        self._lock = asyncio.Lock()

    def resolve_paths(self) -> ComfyPaths:
        cfg = self.settings.comfyui
        install_dir = Path(cfg.install_dir).expanduser() if cfg.install_dir else Path()
        main_path = Path(cfg.main_path).expanduser() if cfg.main_path else Path()
        python_path = Path(cfg.python_path).expanduser() if cfg.python_path else Path()
        models_dir = Path(cfg.models_dir).expanduser() if cfg.models_dir else Path()

        if main_path.is_file() and python_path.is_file():
            base = main_path.parent
            return ComfyPaths(
                install_dir=install_dir if install_dir.exists() else base,
                main_path=main_path,
                python_path=python_path,
                models_dir=self._pick_models_dir(models_dir, base),
                input_dir=self._pick_io_dir(cfg.input_dir, base / "input", "comfyui_input"),
                output_dir=self._pick_io_dir(cfg.output_dir, base / "output", "comfyui_output"),
            )

        detected = self._detect_paths()
        if detected is None:
            raise ComfyConnectionError(
                "ComfyUI 설치를 찾을 수 없습니다. config/settings.yaml의 comfyui.install_dir / main_path / python_path를 확인해 주세요."
            )
        return detected

    def _detect_paths(self) -> ComfyPaths | None:
        local_appdata = Path(os.environ.get("LOCALAPPDATA", ""))
        candidates = [
            Path(self.settings.comfyui.install_dir).expanduser() if self.settings.comfyui.install_dir else None,
            local_appdata / "Comfy-Desktop" / "ComfyUI-Installs" / "ComfyUI",
            local_appdata / "Comfy-Desktop" / "ComfyUI-Installs" / "test",
            Path("C:/ComfyUI_windows_portable"),
            Path("C:/ComfyUI"),
            Path.home() / "ComfyUI",
        ]
        for candidate in candidates:
            if candidate is None or not candidate.exists():
                continue
            if (candidate / "main.py").is_file():
                base = candidate
                install_dir = candidate
            elif (candidate / "ComfyUI" / "main.py").is_file():
                base = candidate / "ComfyUI"
                install_dir = candidate
            else:
                continue

            python_candidates = [
                base / ".venv" / "Scripts" / "python.exe",
                install_dir / "standalone-env" / "python.exe",
                base / "venv" / "Scripts" / "python.exe",
                install_dir / "python_embeded" / "python.exe",
            ]
            python_path = next((p for p in python_candidates if p.is_file()), None)
            if python_path is None:
                python_path = Path(sys.executable)

            configured_models = (
                Path(self.settings.comfyui.models_dir).expanduser()
                if self.settings.comfyui.models_dir
                else Path()
            )
            models_dir = self._pick_models_dir(configured_models, base)
            return ComfyPaths(
                install_dir=install_dir,
                main_path=base / "main.py",
                python_path=python_path,
                models_dir=models_dir,
                input_dir=self._pick_io_dir(
                    self.settings.comfyui.input_dir,
                    base / "input",
                    "comfyui_input",
                ),
                output_dir=self._pick_io_dir(
                    self.settings.comfyui.output_dir,
                    base / "output",
                    "comfyui_output",
                ),
            )
        return None

    def _pick_models_dir(self, configured: Path, base: Path) -> Path:
        local_appdata = Path(os.environ.get("LOCALAPPDATA", ""))
        candidates = [
            configured,
            local_appdata / "Comfy-Desktop" / "ComfyUI-Shared" / "models",
            base / "models",
            base.parent / "models",
        ]
        for candidate in candidates:
            if candidate and candidate.exists():
                return candidate
        return base / "models"

    def _pick_io_dir(self, configured: str, fallback: Path, project_fallback_name: str) -> Path:
        if configured:
            path = Path(configured).expanduser()
            if path.exists():
                return path
        if fallback.exists():
            return fallback
        path = PROJECT_ROOT / "outputs" / project_fallback_name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _write_extra_model_paths(self, models_dir: Path) -> Path:
        path = self.settings.extra_model_paths_path
        path.parent.mkdir(parents=True, exist_ok=True)
        folders = {name: f"{name}/" for name in _MODEL_FOLDERS}
        data = {
            "pixelforge": {
                "base_path": str(models_dir),
                "is_default": True,
                **folders,
            }
        }
        with path.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(data, handle, allow_unicode=True, sort_keys=False)
        return path

    def _port_open(self, host: str, port: int) -> bool:
        try:
            with socket.create_connection((host, port), timeout=0.6):
                return True
        except OSError:
            return False

    def _log_tail(self, limit: int = 60) -> str:
        log_path = self.settings.logs_dir / "comfyui-server.log"
        if not log_path.exists():
            return ""
        try:
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            return "\n".join(lines[-limit:])
        except OSError:
            return ""

    async def ensure_running(self, comfy: ComfyClient) -> None:
        async with self._lock:
            if await comfy.is_connected():
                return
            if not self.settings.comfyui.auto_start:
                raise ComfyConnectionError(
                    f"ComfyUI에 연결할 수 없습니다. ({self.settings.comfyui.normalized_url}) ComfyUI를 실행한 뒤 다시 시도해 주세요."
                )

            paths = self.resolve_paths()
            parsed = urlparse(self.settings.comfyui.normalized_url)
            host = parsed.hostname or "127.0.0.1"
            port = parsed.port or 8188
            if host not in {"127.0.0.1", "localhost", "::1"}:
                raise ComfyConnectionError(
                    "보안을 위해 로컬(127.0.0.1) ComfyUI 주소만 자동 기동할 수 있습니다. config/settings.yaml의 base_url을 확인해 주세요."
                )

            if self._port_open(host, port):
                raise ComfyConnectionError(
                    f"포트 {port}이(가) 사용 중이지만 ComfyUI API가 응답하지 않습니다. 기존 ComfyUI 창을 닫거나 config/settings.yaml의 base_url을 변경해 주세요."
                )

            extra_paths = self._write_extra_model_paths(paths.models_dir)
            self.settings.logs_dir.mkdir(parents=True, exist_ok=True)
            log_path = self.settings.logs_dir / "comfyui-server.log"
            self._log_handle = log_path.open("a", encoding="utf-8", errors="replace")
            self._log_handle.write(
                f"\n\n===== PixelForge Local: ComfyUI start {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n"
            )
            self._log_handle.flush()

            args = [
                str(paths.python_path),
                "-s",
                str(paths.main_path),
                "--disable-auto-launch",
                "--listen",
                "127.0.0.1",
                "--port",
                str(port),
                "--extra-model-paths-config",
                str(extra_paths),
                "--input-directory",
                str(paths.input_dir),
                "--output-directory",
                str(paths.output_dir),
            ]
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            env["HF_HUB_DISABLE_TELEMETRY"] = "1"
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
            self._process = subprocess.Popen(
                args,
                cwd=str(paths.main_path.parent),
                stdout=self._log_handle,
                stderr=subprocess.STDOUT,
                env=env,
                creationflags=creationflags,
            )
            self._started_by_us = True

            deadline = time.monotonic() + max(15, self.settings.comfyui.launch_timeout_seconds)
            while time.monotonic() < deadline:
                if self._process.poll() is not None:
                    tail = self._log_tail()
                    raise ComfyConnectionError(
                        "ComfyUI 기동에 실패했습니다. logs/comfyui-server.log를 확인해 주세요.",
                        detail=tail,
                    )
                if await comfy.is_connected():
                    return
                await asyncio.sleep(1.0)

            raise ComfyConnectionError(
                "ComfyUI 기동 시간이 초과되었습니다. logs/comfyui-server.log를 확인해 주세요.",
                detail=self._log_tail(),
            )

    def shutdown(self) -> None:
        if self._started_by_us and self.settings.comfyui.stop_on_exit and self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=8)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
        if self._log_handle:
            try:
                self._log_handle.close()
            except Exception:
                pass
            self._log_handle = None
