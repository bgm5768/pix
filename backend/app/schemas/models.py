from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


OutputSize = Literal[16, 32, 64, 96, 128]
PostProcessMode = Literal["quantize", "nearest", "posterize"]
AssetMode = Literal["icon", "character", "object", "tile"]
ResizeFilter = Literal["nearest", "box", "lanczos"]
GenerateKind = Literal["pixel", "image"]
ModelCategory = Literal["pixel", "image", "other"]
ImageSize = Literal[512, 768, 1024]


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    negative_prompt: str | None = Field(default=None, max_length=2000)
    mode: AssetMode = "icon"
    output_size: OutputSize = 64
    seed: int | None = Field(default=None, ge=0, le=4_294_967_295)
    steps: int = Field(default=28, ge=8, le=60)
    cfg: float = Field(default=6.0, ge=1.0, le=15.0)
    lora_strength: float = Field(default=0.8, ge=0.0, le=3.0)
    transparent: bool = True
    postprocess: PostProcessMode = "quantize"
    palette_colors: int = Field(default=16, ge=0, le=64)
    resize_filter: ResizeFilter = "nearest"
    candidates: int = Field(default=4, ge=1, le=8)
    # ``pixel`` runs the pixel-art prompt/postprocess pipeline. ``image``
    # keeps the native SDXL output and skips pixel postprocessing.
    kind: GenerateKind = "pixel"
    image_size: ImageSize = 1024
    # Optional per-request model override.  None (or an empty checkpoint)
    # keeps the server default from config/settings.yaml.  An empty LoRA
    # string explicitly disables the LoRA for this request.
    checkpoint: str | None = Field(default=None, max_length=255)
    lora: str | None = Field(default=None, max_length=255)
    # Image page: translate a Korean prompt into English before generation.
    # Pixel prompts keep using the deterministic prompt engine.
    translate_prompt: bool = True

    @field_validator("prompt")
    @classmethod
    def _prompt_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("프롬프트를 입력해 주세요.")
        return value

    @field_validator("negative_prompt")
    @classmethod
    def _negative_strip(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class JobStatus(str, Enum):
    QUEUED = "queued"
    PREPARING = "preparing"
    GENERATING = "generating"
    POSTPROCESSING = "postprocessing"
    COMPLETED = "completed"
    ERROR = "error"
    CANCELLED = "cancelled"


class QualityCheck(BaseModel):
    key: str
    label: str
    passed: bool
    value: str = ""
    message: str = ""


class PromptPlanView(BaseModel):
    asset_type: str
    subject: str
    view: str
    composition: str
    style: str
    background: str
    detail_level: str
    palette: str
    output_resolution: int
    mode: str
    source: str
    positive: str
    negative: str


class ResultInfo(BaseModel):
    original_url: str
    cutout_url: str | None = None
    crop_url: str | None = None
    pixel_url: str | None = None
    preview_url: str
    image_url: str | None = None
    image_preview_url: str | None = None
    download_url: str
    width: int
    height: int
    preview_scale: int
    palette_colors: int
    transparent: bool
    postprocess: PostProcessMode
    mode: AssetMode = "icon"
    kind: GenerateKind = "pixel"
    subject_fill: float = 0.0
    resize_filter: ResizeFilter = "nearest"
    quality: list[QualityCheck] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    candidates_generated: int = 1
    candidate_index: int = 0
    candidate_score: float = 0.0
    panel_suspected: bool = False


class JobView(BaseModel):
    job_id: str
    status: JobStatus
    stage_message: str
    progress: int = 0
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    request: GenerateRequest
    seed_used: int | None = None
    base_seed: int | None = None
    prompt_original: str | None = None
    prompt_used: str | None = None
    prompt_translated: bool = False
    negative_used: str | None = None
    comfy_prompt_id: str | None = None
    step: int = 0
    total_steps: int = 0
    queue_position: int = 0
    prompt_plan: PromptPlanView | None = None
    result: ResultInfo | None = None
    error: str | None = None
    error_code: str | None = None


class GenerateResponse(BaseModel):
    job_id: str
    status: JobStatus
    queue_position: int = 0


class CancelResponse(BaseModel):
    job_id: str
    status: JobStatus
    message: str


class ModelAvailability(BaseModel):
    name: str
    available: bool


class ModelFile(BaseModel):
    name: str
    size_bytes: int = 0
    compatible: bool = True
    category: ModelCategory = "image"


class ModelStatus(BaseModel):
    checkpoint: ModelAvailability
    lora: ModelAvailability
    # Full catalogs from ComfyUI.  Sizes come from the local models directory
    # and ``compatible`` flags files that are not SDXL text-to-image models
    # (for example hunyuan3d or segmentation checkpoints).
    checkpoints: list[ModelFile] = Field(default_factory=list)
    loras: list[ModelFile] = Field(default_factory=list)


class ModelDownloadItem(BaseModel):
    id: str
    label: str
    kind: Literal["checkpoint", "lora"]
    filename: str
    description: str = ""
    trigger: str | None = None
    recommended_strength: float | None = None
    size_bytes: int = 0
    status: Literal["not_installed", "downloading", "installed", "error", "cancelled"] = "not_installed"
    progress: float = 0.0
    downloaded_bytes: int = 0
    speed_bps: float = 0.0
    error: str | None = None


class ModelCatalogResponse(BaseModel):
    items: list[ModelDownloadItem] = Field(default_factory=list)
    models_dir: str = ""


class ComfyStatus(BaseModel):
    connected: bool
    url: str
    version: str | None = None
    error: str | None = None


class GpuStatus(BaseModel):
    name: str
    vram_total: int = 0
    vram_free: int = 0
    state: str = "idle"


class QueueStatus(BaseModel):
    active: int = 0
    pending: int = 0


class HealthResponse(BaseModel):
    status: str = "ok"
    app_version: str
    comfyui: ComfyStatus
    gpu: GpuStatus | None = None
    models: ModelStatus
    queue: QueueStatus
    timestamp: datetime


class OutputItem(BaseModel):
    job_id: str
    pixel_url: str | None = None
    image_url: str | None = None
    preview_url: str
    original_url: str
    cutout_url: str | None = None
    crop_url: str | None = None
    download_url: str
    width: int
    height: int
    created_at: datetime
    prompt: str = ""
    seed: int | None = None
    transparent: bool = False
    postprocess: PostProcessMode = "quantize"
    mode: AssetMode = "icon"
    kind: GenerateKind = "pixel"
    output_size: int
    palette_colors: int = 0
    subject_fill: float = 0.0
    resize_filter: ResizeFilter = "nearest"
    quality: list[QualityCheck] = Field(default_factory=list)
    candidates_generated: int = 1
    candidate_index: int = 0
    candidate_score: float = 0.0
    panel_suspected: bool = False


class OutputsResponse(BaseModel):
    items: list[OutputItem]
    total: int


class TranslateRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)

    @field_validator("text")
    @classmethod
    def _text_strip(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("번역할 텍스트를 입력해 주세요.")
        return value


class TranslateResponse(BaseModel):
    source: str
    text: str
    translated: bool
    model: str = "opus-mt-ko-en"
    elapsed_ms: int = 0
    error: str | None = None


class DeleteOutputResponse(BaseModel):
    job_id: str
    deleted: list[str] = Field(default_factory=list)
    count: int = 0
    message: str = "결과를 삭제했습니다."
