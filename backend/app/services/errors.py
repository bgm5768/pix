from __future__ import annotations


class PixelForgeError(Exception):
    """Base class for user-facing application errors."""

    code = "INTERNAL_ERROR"
    status_code = 500

    def __init__(self, message: str, *, code: str | None = None, detail: str | None = None):
        super().__init__(message)
        self.message = message
        self.code = code or self.code
        self.detail = detail

    def to_dict(self) -> dict[str, str | None]:
        return {"code": self.code, "message": self.message, "detail": self.detail}


class ComfyConnectionError(PixelForgeError):
    code = "COMFY_CONNECTION_ERROR"
    status_code = 503


class ComfyExecutionError(PixelForgeError):
    code = "COMFY_EXECUTION_ERROR"
    status_code = 502


class ModelMissingError(PixelForgeError):
    code = "MODEL_MISSING"
    status_code = 409


class ReferenceError(PixelForgeError):
    code = "REFERENCE_ERROR"
    status_code = 400


class ReferenceCompatibilityError(PixelForgeError):
    code = "REFERENCE_UNSUPPORTED"
    status_code = 409


class VramError(PixelForgeError):
    code = "VRAM_OOM"
    status_code = 507


class QueueFullError(PixelForgeError):
    code = "QUEUE_FULL"
    status_code = 429


class JobNotFoundError(PixelForgeError):
    code = "JOB_NOT_FOUND"
    status_code = 404


class JobConflictError(PixelForgeError):
    code = "JOB_CONFLICT"
    status_code = 409


class ModelDownloadError(PixelForgeError):
    code = "MODEL_DOWNLOAD_ERROR"
    status_code = 409


class PostProcessError(PixelForgeError):
    code = "POSTPROCESS_ERROR"
    status_code = 500
