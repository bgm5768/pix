from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from app.config import ComfyConfig
from app.services.errors import ComfyConnectionError, ComfyExecutionError, ModelMissingError, VramError


class ComfyClient:
    """Small async client around the local ComfyUI HTTP API."""

    def __init__(self, config: ComfyConfig):
        self.config = config
        self.base_url = config.normalized_url
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(config.request_timeout_seconds, connect=4.0),
            follow_redirects=True,
        )
        self._model_cache: tuple[float, set[str], set[str]] | None = None
        self._model_cache_ttl = 8.0

    async def close(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = await self._client.request(method, path, **kwargs)
        except httpx.ConnectError as exc:
            raise ComfyConnectionError(
                f"ComfyUI에 연결할 수 없습니다. ({self.base_url}) ComfyUI가 실행 중인지 확인해 주세요.",
                detail=str(exc),
            ) from exc
        except httpx.TimeoutException as exc:
            raise ComfyConnectionError(
                "ComfyUI 응답이 너무 늦습니다. GPU/ComfyUI 상태를 확인해 주세요.",
                detail=str(exc),
            ) from exc
        except httpx.HTTPError as exc:
            raise ComfyConnectionError(
                "ComfyUI 통신 중 오류가 발생했습니다.",
                detail=str(exc),
            ) from exc
        return response

    async def _json(self, method: str, path: str, **kwargs: Any) -> Any:
        response = await self._request(method, path, **kwargs)
        if response.status_code >= 400:
            text = response.text[:800]
            raise ComfyExecutionError(
                f"ComfyUI가 요청을 거부했습니다. (HTTP {response.status_code})",
                detail=text,
            )
        try:
            return response.json()
        except ValueError as exc:
            raise ComfyExecutionError("ComfyUI 응답을 해석할 수 없습니다.", detail=response.text[:500]) from exc

    async def health(self) -> dict[str, Any]:
        return await self._json("GET", "/system_stats")

    async def is_connected(self) -> bool:
        try:
            await self.health()
            return True
        except Exception:
            return False

    async def get_object_info(self, node_class: str | None = None) -> dict[str, Any]:
        path = "/object_info" if node_class is None else f"/object_info/{node_class}"
        return await self._json("GET", path)

    async def get_available_models(self, force: bool = False) -> tuple[set[str], set[str]]:
        now = time.monotonic()
        if not force and self._model_cache and now - self._model_cache[0] < self._model_cache_ttl:
            return self._model_cache[1], self._model_cache[2]
        try:
            checkpoints, loras = await asyncio.gather(
                self.get_object_info("CheckpointLoaderSimple"),
                self.get_object_info("LoraLoader"),
            )
            ckpt_names = set(checkpoints["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0])
            lora_names = set(loras["LoraLoader"]["input"]["required"]["lora_name"][0])
        except Exception:
            # Health endpoint should still work when object_info is temporarily unavailable.
            if self._model_cache:
                return self._model_cache[1], self._model_cache[2]
            raise
        self._model_cache = (now, ckpt_names, lora_names)
        return ckpt_names, lora_names

    async def queue_prompt(self, workflow: dict[str, Any], client_id: str) -> str:
        payload = {"prompt": workflow, "client_id": client_id}
        response = await self._request("POST", "/prompt", json=payload)
        try:
            data = response.json()
        except ValueError:
            data = {}
        if response.status_code >= 400 or data.get("error") or data.get("node_errors"):
            message = self._format_prompt_error(data, response.status_code)
            lowered = message.lower()
            if "out of memory" in lowered or "allocation on device" in lowered:
                raise VramError(
                    "GPU VRAM이 부족해 이미지를 생성할 수 없습니다. 해상도나 스텝을 낮추고 다시 시도해 주세요.",
                    detail=message,
                )
            if "not in list" in lowered or "value_not_in_list" in lowered:
                raise ModelMissingError(
                    "필요한 모델(체크포인트 또는 LoRA)을 ComfyUI에서 찾을 수 없습니다. 모델 파일과 ComfyUI 모델 경로를 확인해 주세요.",
                    detail=message,
                )
            raise ComfyExecutionError("ComfyUI가 프롬프트를 거부했습니다.", detail=message)
        prompt_id = data.get("prompt_id")
        if not prompt_id:
            raise ComfyExecutionError("ComfyUI가 작업 ID를 반환하지 않았습니다.", detail=str(data)[:800])
        return str(prompt_id)

    async def get_history(self, prompt_id: str) -> dict[str, Any] | None:
        data = await self._json("GET", f"/history/{prompt_id}")
        if not isinstance(data, dict):
            return None
        entry = data.get(prompt_id)
        return entry if isinstance(entry, dict) else None

    async def get_queue(self) -> dict[str, Any]:
        return await self._json("GET", "/queue")

    async def interrupt(self) -> None:
        try:
            await self._request("POST", "/interrupt")
        except ComfyConnectionError:
            pass

    async def delete_queue_items(self, prompt_ids: list[str]) -> None:
        if not prompt_ids:
            return
        try:
            await self._request("POST", "/queue", json={"delete": prompt_ids})
        except ComfyConnectionError:
            pass

    async def view_image(self, filename: str, subfolder: str = "", image_type: str = "output") -> bytes:
        response = await self._request(
            "GET",
            "/view",
            params={"filename": filename, "subfolder": subfolder, "type": image_type},
        )
        if response.status_code >= 400:
            raise ComfyExecutionError(
                "ComfyUI에서 생성 이미지를 가져오지 못했습니다.",
                detail=response.text[:500],
            )
        return response.content

    @staticmethod
    def extract_execution_error(entry: dict[str, Any]) -> tuple[str, str | None]:
        """Return (message, code) from a ComfyUI history entry."""
        status = entry.get("status") or {}
        messages = status.get("messages") or []
        for item in messages:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            event_type, data = item[0], item[1]
            if event_type in {"execution_error", "execution_interrupted"}:
                if not isinstance(data, dict):
                    continue
                message = str(
                    data.get("exception_message")
                    or data.get("message")
                    or ("실행이 중단되었습니다." if event_type == "execution_interrupted" else "ComfyUI 실행 오류")
                )
                lowered = message.lower()
                if "out of memory" in lowered or "allocation on device" in lowered:
                    return (
                        "GPU VRAM이 부족합니다. 출력 해상도나 스텝을 낮추고, 다른 GPU 작업을 종료한 뒤 다시 시도해 주세요.",
                        "VRAM_OOM",
                    )
                node = data.get("node_type") or data.get("node_id") or "알 수 없는 노드"
                return f"ComfyUI 생성 중 오류가 발생했습니다. ({node}) {message}", "COMFY_EXECUTION_ERROR"
        if status.get("status_str") == "error":
            return "ComfyUI 생성에 실패했습니다. ComfyUI 콘솔 로그를 확인해 주세요.", "COMFY_EXECUTION_ERROR"
        return "ComfyUI 생성이 중단되었습니다.", "COMFY_EXECUTION_ERROR"

    @staticmethod
    def _format_prompt_error(data: dict[str, Any], status_code: int) -> str:
        parts: list[str] = []
        error = data.get("error")
        if isinstance(error, dict):
            parts.append(str(error.get("message") or error.get("type") or "프롬프트 오류"))
            if error.get("details"):
                parts.append(str(error["details"]))
        elif error:
            parts.append(str(error))
        node_errors = data.get("node_errors")
        if isinstance(node_errors, dict):
            for node_id, node_data in node_errors.items():
                if not isinstance(node_data, dict):
                    continue
                for item in node_data.get("errors") or []:
                    if isinstance(item, dict):
                        text = item.get("details") or item.get("message") or ""
                        if text:
                            parts.append(f"노드 {node_id}: {text}")
        if not parts:
            parts.append(f"HTTP {status_code}")
        return " | ".join(parts)[:1200]
