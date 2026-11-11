from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import time
from dataclasses import dataclass
from typing import Any

import psutil

from app.schemas.models import GpuStatus, MemoryStatus

logger = logging.getLogger("pixelforge.system")

_WINDOWS_CREATE_NO_WINDOW = 0x08000000
_QUERY_FIELDS = (
    "name",
    "utilization.gpu",
    "memory.used",
    "memory.total",
    "temperature.gpu",
    "power.draw",
    "power.limit",
)


def _number(value: str) -> float | None:
    value = value.strip()
    if not value or value.upper() in {"N/A", "[N/A]", "NOT SUPPORTED"}:
        return None
    try:
        return float(value)
    except ValueError:
        return None


@dataclass
class _Snapshot:
    gpu: GpuStatus | None
    memory: MemoryStatus | None
    sampled_at: float


class SystemMonitor:
    """Cheap GPU/VRAM/RAM sampler for the status bar.

    ``nvidia-smi`` is used when available because ComfyUI's ``system_stats``
    only exposes VRAM, not utilization, temperature, or power.  Results are
    cached briefly so several clients polling the UI share one sample.
    """

    def __init__(self, cache_seconds: float = 1.5):
        self.cache_seconds = cache_seconds
        self._lock = asyncio.Lock()
        self._snapshot: _Snapshot | None = None

    async def snapshot(self) -> tuple[GpuStatus | None, MemoryStatus | None]:
        now = time.monotonic()
        current = self._snapshot
        if current is not None and now - current.sampled_at < self.cache_seconds:
            return current.gpu, current.memory

        async with self._lock:
            current = self._snapshot
            now = time.monotonic()
            if current is not None and now - current.sampled_at < self.cache_seconds:
                return current.gpu, current.memory
            gpu = await asyncio.to_thread(self._read_gpu)
            memory = await asyncio.to_thread(self._read_memory)
            self._snapshot = _Snapshot(gpu=gpu, memory=memory, sampled_at=time.monotonic())
            return gpu, memory

    @staticmethod
    def _nvidia_smi() -> str | None:
        executable = shutil.which("nvidia-smi")
        if executable:
            return executable
        for candidate in (
            r"C:\Windows\System32\nvidia-smi.exe",
            r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe",
        ):
            try:
                from pathlib import Path

                if Path(candidate).is_file():
                    return candidate
            except OSError:
                continue
        return None

    def _read_gpu(self) -> GpuStatus | None:
        executable = self._nvidia_smi()
        if not executable:
            return None
        command = [
            executable,
            f"--query-gpu={','.join(_QUERY_FIELDS)}",
            "--format=csv,noheader,nounits",
        ]
        kwargs: dict[str, Any] = {
            "capture_output": True,
            "text": True,
            "timeout": 2.5,
            "check": False,
        }
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            kwargs["creationflags"] = _WINDOWS_CREATE_NO_WINDOW
        try:
            result = subprocess.run(command, **kwargs)
        except (OSError, subprocess.SubprocessError) as exc:
            logger.debug("nvidia-smi failed: %s", exc)
            return None
        if result.returncode != 0:
            return None
        line = next((line for line in result.stdout.splitlines() if line.strip()), "")
        if not line:
            return None
        # GPU names can contain commas; split from the right for the numeric tail.
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < len(_QUERY_FIELDS):
            return None
        tail = parts[-(len(_QUERY_FIELDS) - 1):]
        name = ", ".join(parts[: -(len(_QUERY_FIELDS) - 1)]).strip() or "GPU"
        utilization = _number(tail[0])
        used = _number(tail[1])
        total = _number(tail[2])
        temperature = _number(tail[3])
        power = _number(tail[4])
        power_limit = _number(tail[5])
        used_bytes = int((used or 0) * 1024 * 1024)
        total_bytes = int((total or 0) * 1024 * 1024)
        return GpuStatus(
            name=name,
            vram_total=total_bytes,
            vram_used=used_bytes,
            vram_free=max(0, total_bytes - used_bytes),
            utilization=utilization,
            temperature_c=temperature,
            power_w=power,
            power_limit_w=power_limit,
            source="nvidia-smi",
        )

    @staticmethod
    def _read_memory() -> MemoryStatus | None:
        try:
            memory = psutil.virtual_memory()
        except Exception as exc:
            logger.debug("psutil memory read failed: %s", exc)
            return None
        return MemoryStatus(
            total=int(memory.total),
            used=int(memory.used),
            available=int(memory.available),
            percent=round(float(memory.percent), 1),
        )
