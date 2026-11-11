from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class AppConfig(BaseModel):
    name: str = "PixelForge Local"
    version: str = "1.0.0"
    host: str = "127.0.0.1"
    port: int = 8765
    open_browser: bool = True
    # Origins allowed to call this backend. GitHub Pages needs to be listed
    # explicitly because it is served over HTTPS while the backend stays local.
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            "http://127.0.0.1:8765",
            "http://localhost:8765",
            "https://bgm5768.github.io",
        ]
    )


class ComfyConfig(BaseModel):
    base_url: str = "http://127.0.0.1:8188"
    auto_start: bool = True
    stop_on_exit: bool = False
    install_dir: str = ""
    python_path: str = ""
    main_path: str = ""
    models_dir: str = ""
    input_dir: str = ""
    output_dir: str = ""
    launch_timeout_seconds: int = 120
    request_timeout_seconds: float = 20.0
    job_timeout_seconds: int = 300
    extra_model_paths_file: str = "config/comfyui_model_paths.generated.yaml"

    @property
    def normalized_url(self) -> str:
        return self.base_url.rstrip("/")

    @property
    def ws_url(self) -> str:
        if self.normalized_url.startswith("https://"):
            return "wss://" + self.normalized_url[len("https://") :]
        if self.normalized_url.startswith("http://"):
            return "ws://" + self.normalized_url[len("http://") :]
        return self.normalized_url


class GenerationConfig(BaseModel):
    workflow_file: str = "workflows/text_to_pixel.json"
    checkpoint: str = "sd_xl_base_1.0.safetensors"
    lora: str = "pixel-art-xl.safetensors"
    base_width: int = 512
    base_height: int = 512
    steps: int = 28
    cfg: float = 6.0
    sampler: str = "dpmpp_2m"
    scheduler: str = "karras"
    lora_strength: float = 0.8
    output_sizes: list[int] = Field(default_factory=lambda: [16, 32, 64, 96, 128])
    default_output_size: int = 64
    default_postprocess: str = "quantize"
    palette_colors: int = 16
    default_palette_colors: int = 16
    default_resize_filter: str = "nearest"
    # Generate several seeds and keep the best-scoring one. Tile mode stays at
    # one image because a repeating texture has no single-subject composition.
    default_candidates: int = 4
    max_candidates: int = 8
    # Image generator page: native SDXL output without pixel postprocessing.
    default_image_size: int = 1024
    image_sizes: list[int] = Field(default_factory=lambda: [512, 768, 1024])
    image_checkpoint: str = "sd_xl_base_1.0.safetensors"
    image_lora: str = ""
    image_default_candidates: int = 1
    image_negative_prompt: str = ""
    # Reference page: IP-Adapter Plus on top of an SDXL checkpoint.
    reference_checkpoint: str = "sd_xl_base_1.0.safetensors"
    reference_lora: str = ""
    reference_default_size: int = 1024
    reference_default_strength: float = 0.85
    reference_default_focus: str = "appearance"
    reference_max_references: int = 5
    transparent_default: bool = True
    # Local background segmentation (rembg/u2net, CPU). Padding gives u2net
    # enough context to segment pixel-art icons that fill the frame.
    rembg_enabled: bool = True
    rembg_model: str = "u2net"
    rembg_pad_ratio: float = 0.25
    rembg_min_ratio: float = 0.02
    rembg_max_ratio: float = 0.985
    # Flat border colour key, used to cut sprite-sheet seams and as fallback.
    background_key_tolerance: float = 28.0
    background_key_min_dominance: float = 0.50
    alpha_threshold: int = 128
    min_opaque_ratio: float = 0.03
    # Subject fill targets (largest bbox dimension / canvas dimension).
    subject_fill_icon: float = 0.80
    subject_fill_character: float = 0.86
    subject_fill_object: float = 0.82
    # Optional local LLM prompt structuring (Ollama HTTP API). When it is not
    # running the template engine is used with no noticeable delay.
    prompt_llm_enabled: bool = True
    prompt_llm_url: str = "http://127.0.0.1:11434"
    prompt_llm_model: str = ""
    prompt_llm_timeout_seconds: float = 2.0
    style_prompt: str = ""
    transparent_prompt: str = ""
    negative_prompt: str = ""


class TranslationConfig(BaseModel):
    enabled: bool = True
    # Offline ONNX build of Helsinki-NLP/opus-mt-ko-en (quantized).
    model_dir: str = "models/translation/opus-mt-ko-en"
    max_new_tokens: int = 256
    cache_size: int = 256


class StorageConfig(BaseModel):
    originals_dir: str = "outputs/originals"
    pixel_dir: str = "outputs/pixel_art"
    previews_dir: str = "outputs/previews"
    images_dir: str = "outputs/images"
    image_previews_dir: str = "outputs/image_previews"
    metadata_dir: str = "outputs/metadata"
    jobs_dir: str = "outputs/jobs"
    cutouts_dir: str = "outputs/cutouts"
    crops_dir: str = "outputs/crops"
    candidates_dir: str = "outputs/candidates"
    references_dir: str = "outputs/references"
    reference_samples_dir: str = "assets/references/samples"
    comic_pages_dir: str = "outputs/comic_pages"
    logs_dir: str = "logs"


class JobsConfig(BaseModel):
    max_pending: int = 2
    poll_interval_seconds: float = 0.7
    # Job snapshots are kept so the UI can list recent work after a restart.
    history_limit: int = 50


class StudioConfig(BaseModel):
    """nk comic studio (nk ep web) integration."""

    # Folder that holds nk.py (the comic maker kit).
    kit_path: str = r"C:\nk"
    # Port the studio server listens on. 8765 is PixelForge's own port, so the
    # studio gets its own one and is reached through /studio/.
    port: int = 8766
    # Python that can run nk (needs numpy/cv2/PIL/pyyaml).
    python: str = ""


class Settings(BaseModel):
    app: AppConfig = Field(default_factory=AppConfig)
    comfyui: ComfyConfig = Field(default_factory=ComfyConfig)
    generation: GenerationConfig = Field(default_factory=GenerationConfig)
    translation: TranslationConfig = Field(default_factory=TranslationConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    jobs: JobsConfig = Field(default_factory=JobsConfig)
    studio: StudioConfig = Field(default_factory=StudioConfig)

    def resolve(self, value: str | Path) -> Path:
        path = Path(value).expanduser()
        if path.is_absolute():
            return path
        return (PROJECT_ROOT / path).resolve()

    @property
    def workflow_path(self) -> Path:
        return self.resolve(self.generation.workflow_file)

    @property
    def originals_dir(self) -> Path:
        return self.resolve(self.storage.originals_dir)

    @property
    def pixel_dir(self) -> Path:
        return self.resolve(self.storage.pixel_dir)

    @property
    def previews_dir(self) -> Path:
        return self.resolve(self.storage.previews_dir)

    @property
    def images_dir(self) -> Path:
        return self.resolve(self.storage.images_dir)

    @property
    def image_previews_dir(self) -> Path:
        return self.resolve(self.storage.image_previews_dir)

    @property
    def metadata_dir(self) -> Path:
        return self.resolve(self.storage.metadata_dir)

    @property
    def jobs_dir(self) -> Path:
        return self.resolve(self.storage.jobs_dir)

    @property
    def cutouts_dir(self) -> Path:
        return self.resolve(self.storage.cutouts_dir)

    @property
    def crops_dir(self) -> Path:
        return self.resolve(self.storage.crops_dir)

    @property
    def candidates_dir(self) -> Path:
        return self.resolve(self.storage.candidates_dir)

    @property
    def references_dir(self) -> Path:
        return self.resolve(self.storage.references_dir)

    @property
    def reference_uploads_dir(self) -> Path:
        return self.references_dir / "uploads"

    @property
    def reference_samples_dir(self) -> Path:
        return self.resolve(self.storage.reference_samples_dir)

    @property
    def comic_pages_dir(self) -> Path:
        return self.resolve(self.storage.comic_pages_dir)

    @property
    def logs_dir(self) -> Path:
        return self.resolve(self.storage.logs_dir)

    @property
    def extra_model_paths_path(self) -> Path:
        return self.resolve(self.comfyui.extra_model_paths_file)

    @property
    def translation_model_dir(self) -> Path:
        return self.resolve(self.translation.model_dir)

    def ensure_directories(self) -> None:
        for path in (
            self.originals_dir,
            self.pixel_dir,
            self.previews_dir,
            self.images_dir,
            self.image_previews_dir,
            self.metadata_dir,
            self.jobs_dir,
            self.cutouts_dir,
            self.crops_dir,
            self.candidates_dir,
            self.reference_uploads_dir,
            self.reference_samples_dir,
            self.comic_pages_dir,
            self.logs_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"설정 파일을 찾을 수 없습니다: {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"설정 파일 형식이 올바르지 않습니다: {path}")
    return data


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    config_path = Path(os.environ.get("PIXELFORGE_CONFIG", PROJECT_ROOT / "config" / "settings.yaml"))
    data = _read_yaml(config_path)
    settings = Settings.model_validate(data)
    settings.ensure_directories()
    return settings


def reload_settings() -> Settings:
    get_settings.cache_clear()
    return get_settings()
