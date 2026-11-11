from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ModelKind = Literal["checkpoint", "lora"]


@dataclass(frozen=True)
class ModelNote:
    """Human-readable metadata shown next to a model in the UI.

    The app can list any file ComfyUI exposes, so this is intentionally a
    lookup table instead of a required sidecar file: unknown models still work
    and simply fall back to a generic description.
    """

    kind: ModelKind
    description: str
    features: tuple[str, ...] = ()
    trigger: str | None = None
    prompt_tip: str | None = None
    # LoRA slider strength and checkpoint sampler settings shown by the
    # "optimal values" button in the settings panel.
    recommended_strength: float | None = None
    recommended_steps: int | None = None
    recommended_cfg: float | None = None
    base_model: str = "SDXL 1.0"
    nsfw: bool = False
    vram_hint: str = "12GB VRAM"


NOTES: dict[str, ModelNote] = {
    # --- installed checkpoints ------------------------------------------------
    "sd_xl_base_1.0.safetensors": ModelNote(
        kind="checkpoint",
        description="SDXL 1.0 공식 베이스 · 호환성이 가장 좋은 범용 모델",
        features=("범용", "SDXL 표준", "프롬프트 충실도", "풍경/인물"),
        recommended_steps=30,
        recommended_cfg=7.0,
    ),
    "noobai-xl-v1.0.safetensors": ModelNote(
        kind="checkpoint",
        description="NoobAI-XL 1.0 · Danbooru 태그 기반 애니/일러스트 특화 모델",
        features=("애니", "일러스트", "캐릭터", "태그 프롬프트"),
        prompt_tip="masterpiece, best quality, 캐릭터 태그",
        recommended_steps=28,
        recommended_cfg=5.5,
        nsfw=True,
    ),
    "lustifysdxlnsfwsfw_v20.safetensors": ModelNote(
        kind="checkpoint",
        description="LUSTIFY! v2.0 · 인물 피부와 조명에 강한 무검열 포토리얼 모델",
        features=("포토리얼", "NSFW/SFW", "인물", "상업적 사용 가능"),
        recommended_steps=30,
        recommended_cfg=5.5,
        nsfw=True,
    ),
    "sdxl1.0_pixelartdiffusionxl_spriteshaper.safetensors": ModelNote(
        kind="checkpoint",
        description="PixelArtDiffusionXL · SpriteShaper 픽셀아트/스프라이트 특화",
        features=("픽셀", "스프라이트", "게임 에셋", "제한 팔레트"),
        recommended_steps=30,
        recommended_cfg=7.0,
    ),
    # --- installed LoRAs ------------------------------------------------------
    "pixel-art-xl.safetensors": ModelNote(
        kind="lora",
        description="SDXL 픽셀아트 LoRA · 도트/스프라이트 스타일을 강화",
        features=("픽셀", "도트", "게임 스프라이트", "가벼운 파일"),
        trigger="pixel art",
        recommended_strength=0.8,
    ),
    "pixelartredmond-lite64.safetensors": ModelNote(
        kind="lora",
        description="PixelArtRedmond Lite64 · 픽셀아트 전용 경량 LoRA",
        features=("픽셀", "도트", "SDXL 1.0", "가벼운 파일"),
        recommended_strength=0.8,
    ),
    "pixel-art-sdxl-dora-v0-9.safetensors": ModelNote(
        kind="lora",
        description="Pixel Art SDXL DoRA v0.9 · 강한 스타일화 픽셀 LoRA",
        features=("픽셀", "DoRA", "강한 스타일", "게임 에셋"),
        recommended_strength=0.85,
    ),
    "pixel-art-lora-sdxl.safetensors": ModelNote(
        kind="lora",
        description="Pixel Art LoRA SDXL · 가벼운 범용 픽셀아트 LoRA",
        features=("픽셀", "범용", "Apache-2.0", "가벼운 파일"),
        recommended_strength=0.7,
    ),
    "sexy.safetensors": ModelNote(
        kind="lora",
        description="NTC Slider · sexy · NSFW 강도를 조절하는 슬라이더 LoRA",
        features=("NSFW 슬라이더", "강도 조절", "MIT", "8MB"),
        trigger="sexy",
        recommended_strength=1.2,
        nsfw=True,
    ),
    # --- uncensored checkpoints ----------------------------------------------
    "ponydiffusionv6xl_v6startwiththisone.safetensors": ModelNote(
        kind="checkpoint",
        description="Pony Diffusion V6 XL · 애니/만화·furry에 강한 무검열 SDXL 모델",
        features=("애니/만화", "furry", "강한 명암", "태그 프롬프트"),
        prompt_tip="score_9, score_8_up, score_7_up",
        recommended_steps=30,
        recommended_cfg=7.0,
        nsfw=True,
    ),
    "cyberrealisticxlplay_v10.0_fp16.safetensors": ModelNote(
        kind="checkpoint",
        description="CyberRealistic XL v10.0 · 인물 피부/조명에 강한 무검열 포토리얼 모델",
        features=("포토리얼", "인물", "피부 질감", "NSFW/SFW"),
        recommended_steps=30,
        recommended_cfg=5.0,
        nsfw=True,
    ),
    "epicrealismxl_v7finaldestination.safetensors": ModelNote(
        kind="checkpoint",
        description="epiCRealism XL v7 · 시네마틱 실사와 자연광 인물에 강한 모델",
        features=("포토리얼", "시네마틱", "자연광", "인물"),
        recommended_steps=30,
        recommended_cfg=5.5,
        nsfw=True,
    ),
    "realvisxl_v5.0_fp16.safetensors": ModelNote(
        kind="checkpoint",
        description="RealVisXL V5.0 · 선명한 실사 결과물을 위한 범용 포토리얼 모델",
        features=("포토리얼", "범용", "풍경/인물", "선명한 디테일"),
        recommended_steps=30,
        recommended_cfg=5.0,
        nsfw=True,
    ),
    # --- style / quality LoRAs ------------------------------------------------
    "extremely detailed.safetensors": ModelNote(
        kind="lora",
        description="NTC extremely detailed · 디테일과 질감을 끌어올리는 슬라이더 LoRA",
        features=("디테일 강화", "질감", "미세 묘사", "MIT"),
        trigger="extremely detailed",
        recommended_strength=1.0,
    ),
    "raw.safetensors": ModelNote(
        kind="lora",
        description="NTC raw · 사진 원본 같은 거친 질감과 대비를 만드는 LoRA",
        features=("사진 질감", "강한 대비", "피부 표현", "MIT"),
        trigger="raw",
        recommended_strength=1.0,
    ),
    "filmgrainredmond-filmgrain-filmgrainaf.safetensors": ModelNote(
        kind="lora",
        description="FilmGrain Redmond · 아날로그 필름 그레인과 색감을 더하는 LoRA",
        features=("필름 그레인", "아날로그 색감", "인물/풍경", "170MB"),
        trigger="Film Grain, FilmGrainAF",
        recommended_strength=0.8,
    ),
    "selfiephotographyredmond.safetensors": ModelNote(
        kind="lora",
        description="Selfie Photography Redmond · 셀카/인물 사진 느낌을 만드는 LoRA",
        features=("셀카", "인물 사진", "실사 피부", "SNS 느낌"),
        trigger="instagram model",
        recommended_strength=0.8,
    ),
    "analogredmondv2-analog-analogredmaf.safetensors": ModelNote(
        kind="lora",
        description="Analog Redmond V2 · 필름 카메라 아날로그 사진 스타일 LoRA",
        features=("아날로그", "필름 카메라", "빈티지 색감", "인물/풍경"),
        trigger="AnalogRedmAF, Analog",
        recommended_strength=0.8,
    ),
}


def _normalize(filename: str) -> str:
    return filename.replace("\\", "/").rsplit("/", 1)[-1].strip().lower()


def note_for(filename: str | None) -> ModelNote | None:
    if not filename:
        return None
    return NOTES.get(_normalize(filename))


def checkpoint_recommendation(filename: str | None) -> tuple[int, float]:
    """Return (steps, CFG) that work well for a checkpoint.

    Known files use the curated values above.  Files installed later still get
    a sensible family-based fallback instead of the generic global defaults.
    """
    note = note_for(filename)
    if (
        note is not None
        and note.recommended_steps is not None
        and note.recommended_cfg is not None
    ):
        return note.recommended_steps, note.recommended_cfg

    lowered = _normalize(filename or "")
    if any(token in lowered for token in ("pony", "noob", "illustrious", "animagine")):
        return 28, 5.5
    if any(
        token in lowered
        for token in ("real", "photo", "cyber", "epic", "lustify", "juggernaut")
    ):
        return 30, 5.0
    if any(token in lowered for token in ("pixel", "sprite", "dot")):
        return 30, 7.0
    return 28, 6.0


def lora_triggers() -> dict[str, str]:
    """Map lowercase LoRA filenames to their trigger words."""
    return {
        filename: note.trigger
        for filename, note in NOTES.items()
        if note.kind == "lora" and note.trigger
    }
