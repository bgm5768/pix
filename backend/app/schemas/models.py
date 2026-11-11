from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


OutputSize = Literal[16, 32, 64, 96, 128]
PostProcessMode = Literal["quantize", "nearest", "posterize"]
AssetMode = Literal["icon", "character", "object", "tile"]
ResizeFilter = Literal["nearest", "box", "lanczos"]
GenerateKind = Literal["pixel", "image", "reference"]
ModelCategory = Literal["pixel", "image", "other"]
ImageSize = Literal[512, 768, 1024]
ReferenceFocus = Literal["appearance", "face", "style", "pose", "composition"]
# Face identity engines. ``none`` keeps plain IP-Adapter behaviour, while
# InstantID/PuLID keep the face of one reference image.
IdentityEngine = Literal["none", "instantid", "pulid"]
IdentityMethod = Literal["fidelity", "style", "neutral"]


class ReferenceInput(BaseModel):
    """A stored reference image plus its IP-Adapter strength/focus."""

    asset_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
    strength: float = Field(default=0.85, ge=0.0, le=1.5)
    focus: ReferenceFocus = "appearance"


class ReferenceAnalysis(BaseModel):
    width: int = 0
    height: int = 0
    orientation: Literal["portrait", "landscape", "square"] = "square"
    brightness: float = 0.0
    saturation: float = 0.0
    colorfulness: float = 0.0
    dominant_colors: list[str] = Field(default_factory=list)
    subject_hint: str = ""
    summary: str = ""


class ReferenceAsset(BaseModel):
    id: str
    name: str
    url: str
    source: Literal["upload", "sample"] = "upload"
    width: int = 0
    height: int = 0
    size_bytes: int = 0
    hint: str = ""
    analysis: ReferenceAnalysis = Field(default_factory=ReferenceAnalysis)


class ReferenceUsage(BaseModel):
    asset_id: str
    name: str
    url: str
    focus: ReferenceFocus = "appearance"
    strength: float = 0.85
    analysis_summary: str = ""


class IdentityUsage(BaseModel):
    """Face identity engine applied to a reference job."""

    engine: IdentityEngine = "none"
    image: str | None = None
    name: str = ""
    url: str = ""
    weight: float = 0.0
    method: IdentityMethod = "fidelity"
    control_weight: float = 0.0
    noise: float = 0.0
    include_style: bool = False


class ReferenceSamplesResponse(BaseModel):
    items: list[ReferenceAsset] = Field(default_factory=list)


class ReferenceCapabilities(BaseModel):
    available: bool = False
    node_installed: bool = False
    advanced_node_installed: bool = False
    plus_model: bool = False
    plus_face_model: bool = False
    clip_vision_model: bool = False
    ipadapter_models: list[str] = Field(default_factory=list)
    clip_vision_models: list[str] = Field(default_factory=list)
    checkpoint: str | None = None
    checkpoint_compatible: bool | None = None
    checkpoint_note: str = ""
    guidance: str = ""
    install_hint: str = ""
    instantid_note: str = ""
    pulid_note: str = ""
    max_references: int = 5
    presets: list[str] = Field(default_factory=list)
    # Face identity engines (InstantID / PuLID).
    instantid_available: bool = False
    instantid_node_installed: bool = False
    instantid_model: bool = False
    instantid_controlnet: bool = False
    instantid_models: list[str] = Field(default_factory=list)
    pulid_available: bool = False
    pulid_node_installed: bool = False
    pulid_model: bool = False
    pulid_models: list[str] = Field(default_factory=list)
    insightface_available: bool = False
    insightface_models: list[str] = Field(default_factory=list)
    identity_engines: list[str] = Field(default_factory=list)
    identity_guidance: str = ""


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
    # Reference page: one or more uploaded/sample images. The order is kept
    # when chaining IP-Adapter nodes.
    reference_images: list[ReferenceInput] = Field(default_factory=list, max_length=5)
    # Face identity: keep the face of one reference image with InstantID or
    # PuLID instead of plain IP-Adapter conditioning.
    identity_engine: IdentityEngine = "none"
    identity_image: str | None = Field(default=None, max_length=80)
    identity_weight: float = Field(default=0.85, ge=0.0, le=2.0)
    identity_method: IdentityMethod = "fidelity"
    # InstantID only: how strongly the reference pose/structure is enforced
    # (0 = the prompt decides the pose) and how much noise is injected to avoid
    # the "burned" reference look.
    identity_control_weight: float = Field(default=0.5, ge=0.0, le=5.0)
    identity_noise: float = Field(default=0.35, ge=0.0, le=1.0)
    # When false the identity image is not fed through IP-Adapter as well, so
    # only the face is taken from it and the prompt drives everything else.
    identity_include_style: bool = False

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

    @model_validator(mode="after")
    def _validate_references(self) -> "GenerateRequest":
        if self.kind != "reference":
            if self.identity_engine != "none":
                raise ValueError("얼굴 고정은 레퍼런스 페이지에서만 사용할 수 있습니다.")
            return self
        if not self.reference_images:
            raise ValueError("레퍼런스 이미지를 1장 이상 선택해 주세요.")
        asset_ids = [item.asset_id for item in self.reference_images]
        if len(set(asset_ids)) != len(asset_ids):
            raise ValueError("같은 참고 이미지를 여러 번 선택할 수 없습니다.")
        if self.identity_engine != "none":
            if not self.identity_image:
                raise ValueError("얼굴을 고정할 참고 이미지를 선택해 주세요.")
            if self.identity_image not in asset_ids:
                raise ValueError("얼굴을 고정할 이미지는 참고 이미지 목록에서 골라 주세요.")
        return self


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
    references: list[ReferenceUsage] = Field(default_factory=list)
    identity: IdentityUsage | None = None


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


class JobListResponse(BaseModel):
    items: list[JobView] = Field(default_factory=list)
    active: int = 0
    pending: int = 0


class ModelAvailability(BaseModel):
    name: str
    available: bool


class ModelFile(BaseModel):
    name: str
    size_bytes: int = 0
    compatible: bool = True
    category: ModelCategory = "image"
    description: str = ""
    features: list[str] = Field(default_factory=list)
    trigger: str | None = None
    prompt_tip: str | None = None
    recommended_strength: float | None = None
    recommended_steps: int | None = None
    recommended_cfg: float | None = None
    base_model: str = ""
    nsfw: bool = False
    vram_hint: str = ""


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
    features: list[str] = Field(default_factory=list)
    trigger: str | None = None
    prompt_tip: str | None = None
    recommended_strength: float | None = None
    recommended_steps: int | None = None
    recommended_cfg: float | None = None
    base_model: str = ""
    nsfw: bool = False
    vram_hint: str = ""
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
    vram_used: int = 0
    utilization: float | None = None
    temperature_c: float | None = None
    power_w: float | None = None
    power_limit_w: float | None = None
    source: Literal["nvidia-smi", "comfyui"] = "comfyui"
    state: str = "idle"


class MemoryStatus(BaseModel):
    total: int = 0
    used: int = 0
    available: int = 0
    percent: float = 0.0


class QueueStatus(BaseModel):
    active: int = 0
    pending: int = 0


class SystemStatusResponse(BaseModel):
    gpu: GpuStatus | None = None
    memory: MemoryStatus | None = None
    queue: QueueStatus
    timestamp: datetime


class HealthResponse(BaseModel):
    status: str = "ok"
    app_version: str
    comfyui: ComfyStatus
    gpu: GpuStatus | None = None
    memory: MemoryStatus | None = None
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
    references: list[ReferenceUsage] = Field(default_factory=list)
    identity: IdentityUsage | None = None


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
