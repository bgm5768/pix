from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import asdict, dataclass
from typing import Any

import httpx

logger = logging.getLogger("pixelforge.prompt")

# ---------------------------------------------------------------------------
# Korean -> English vocabulary.
#
# The app is used mostly with short Korean requests ("도서관 아이콘 만들어줘").
# Phrase-level replacements are applied longest-first, then leftover request
# words/particles are removed. Unknown Korean is dropped so SDXL never receives
# untranslatable tokens; the optional local LLM can handle richer requests.
# ---------------------------------------------------------------------------
_PHRASES = {
    # buildings / places
    "도서관 건물": "library building",
    "도서관": "library building",
    "학교 건물": "school building",
    "학교": "school building",
    "병원 건물": "hospital building",
    "병원": "hospital building",
    "식당 건물": "restaurant building",
    "식당": "restaurant building",
    "상점 건물": "shop building",
    "상점": "shop building",
    "가게": "shop building",
    "집": "house",
    "건물": "building",
    "성": "castle",
    "탑": "tower",
    "동굴": "cave",
    "숲": "forest",
    "바다": "sea",
    "산": "mountain",
    # nature / props
    "나무 한 그루": "tree",
    "나무": "tree",
    "돌": "rock",
    "바위": "rock",
    "꽃": "flower",
    "풀": "grass",
    "버섯": "mushroom",
    "상자": "wooden chest",
    "보물 상자": "treasure chest",
    "열쇠": "key",
    "문": "door",
    "창문": "window",
    "책": "book",
    "음식": "food",
    "빵": "bread",
    "케이크": "cake",
    "커피": "coffee cup",
    "물약": "potion bottle",
    "검": "sword",
    "방패": "shield",
    "활": "bow",
    "도끼": "axe",
    "지팡이": "magic staff",
    "무기": "weapon",
    "장식품": "decoration",
    "의자": "chair",
    "책상": "desk",
    "침대": "bed",
    "냉장고": "refrigerator",
    "자동차": "car",
    "차": "car",
    "배": "boat",
    "비행기": "airplane",
    "기차": "train",
    "로봇": "robot",
    "컴퓨터": "computer",
    "전화기": "phone",
    "시계": "clock",
    "램프": "lamp",
    "촛불": "candle",
    "화분": "potted plant",
    # characters
    "고양이": "cat",
    "강아지": "puppy",
    "개": "dog",
    "토끼": "rabbit",
    "여우": "fox",
    "곰": "bear",
    "용": "dragon",
    "드래곤": "dragon",
    "새": "bird",
    "물고기": "fish",
    "기사": "knight",
    "마법사": "wizard",
    "전사": "warrior",
    "궁수": "archer",
    "공주": "princess",
    "왕": "king",
    "좀비": "zombie",
    "해골": "skeleton",
    "로봇 캐릭터": "robot character",
    "캐릭터": "character",
    "사람": "person",
    "남자": "man",
    "여자": "woman",
    "아이": "child",
    # fruit / food
    "빨간색 사과": "red apple",
    "초록색 사과": "green apple",
    "사과": "apple",
    "바나나": "banana",
    "오렌지": "orange",
    "포도": "grapes",
    "딸기": "strawberry",
    "수박": "watermelon",
    "당근": "carrot",
    "감자": "potato",
    # colors / adjectives
    "빨간색": "red",
    "빨간": "red",
    "파란색": "blue",
    "파란": "blue",
    "초록색": "green",
    "초록": "green",
    "노란색": "yellow",
    "노란": "yellow",
    "검은색": "black",
    "검정색": "black",
    "흰색": "white",
    "하얀색": "white",
    "보라색": "purple",
    "분홍색": "pink",
    "주황색": "orange",
    "회색": "gray",
    "갈색": "brown",
    "금색": "gold",
    "은색": "silver",
    "귀여운": "cute",
    "작은": "small",
    "큰": "large",
    "거대한": "huge",
    "날카로운": "sharp",
    "빛나는": "glowing",
    "마법의": "magical",
    "고대의": "ancient",
    "나무로 된": "wooden",
    "돌로 된": "stone",
    "픽셀아트": "",
    "픽셀 아트": "",
    "도트": "",
    # request words
    "만들어줘": "",
    "만들어 줘": "",
    "만들어": "",
    "생성해줘": "",
    "생성해": "",
    "그려줘": "",
    "그려": "",
    "그림": "",
    "이미지": "",
    "아이콘으로": "",
    "아이콘": "",
    "스프라이트": "",
    "배경": "",
    "타일": "",
    "하나만": "",
    "하나": "",
    "한 개": "",
    "한 명": "",
    "한 마리": "",
    "한 그루": "",
    "두 개": "",
    "세 개": "",
    "네 개": "",
    "다섯 개": "",
    "여러 개": "",
    "한": "",
    "그루": "",
    "명": "",
    "마리": "",
    "좀": "",
    "해줘": "",
    "주세요": "",
    "으로": "",
    "로": "",
    "를": "",
    "을": "",
    "이": "",
    "가": "",
    "은": "",
    "는": "",
    "의": "",
    "에": "",
    "와": "",
    "과": "",
}

_STOP_WORDS = {
    "a", "an", "the", "make", "create", "generate", "please", "one", "single",
    "icon", "sprite", "pixel", "art", "mode", "asset", "game", "of", "for",
    "me", "my", "with", "and", "in", "on", "at", "to", "as", "style", "pixelart",
    "image", "picture", "draw", "render",
}

_MODE_VIEW = {
    "icon": "front view",
    "character": "front view",
    "object": "three-quarter view",
    "tile": "top-down view",
}

_MODE_COMPOSITION = {
    "icon": "single centered object, entire object in frame",
    "character": "single centered character, full body visible from head to toe",
    "object": "single centered object, entire object in frame",
    "tile": "seamless repeating pattern",
}

_SUBJECT_HINTS = {
    "library": "with large windows and columns",
    "school": "with a school entrance and bell tower",
    "hospital": "with a medical cross symbol",
    "restaurant": "with a storefront awning",
    "shop": "with a storefront window",
    "house": "with a pitched roof, door and windows",
    "castle": "with stone walls and a gate",
    "tree": "with a trunk and green canopy",
    "apple": "with a stem and leaf",
    "cat": "with pointed ears and a tail",
    "puppy": "with floppy ears and a tail",
    "dog": "with floppy ears and a tail",
    "rabbit": "with long ears",
    "dragon": "with wings and a tail",
    "knight": "wearing armor",
    "wizard": "wearing a pointed hat and robe",
    "sword": "with a blade and hilt",
    "shield": "with a simple emblem",
    "chair": "with four legs and a backrest",
    "desk": "with drawers",
    "bed": "with a pillow and blanket",
    "car": "side view",
    "potion": "in a glass bottle",
    "chest": "with a lid and lock",
    "book": "closed book with a cover",
}

_NEGATIVE_COMMON = (
    "sprite sheet, multiple objects, multiple characters, multiple copies, duplicate, "
    "repeated object, collage, contact sheet, multiple views, split panels, grid layout, "
    "2x2 grid, four panels, icon set, asset pack, collection, set of objects, turnaround, "
    "model sheet, character sheet, text, letters, numbers, labels, watermark, signature, "
    "frame, border, ui, mockup, blurry, photorealistic, 3d render, realistic photo, "
    "excessive gradients, smooth gradient, anti-aliased edges, soft edges, noise, "
    "background scenery, landscape, sky, ground, floor, shadow, vignette, close-up, "
    "portrait, bust, cropped, out of frame"
)

_NEGATIVE_ICON = (
    "background scenery, scene, room, interior, extra objects, extra buildings, "
    "two buildings, people, trees, cars, floating objects, perspective distortion"
)

_NEGATIVE_CHARACTER = (
    "multiple people, group, crowd, extra characters, close-up, portrait, bust, "
    "cropped body, cut off head, cut off feet, out of frame, building, house, castle, "
    "architecture, city, landscape, scenery, room, furniture, ground, shadow"
)

_NEGATIVE_OBJECT = (
    "extra objects, background scenery, scene, room, interior, people, hands, "
    "multiple copies, set, collection"
)

_NEGATIVE_TILE = (
    "text, labels, watermark, frame, border, ui, mockup, single object, centered object, "
    "portrait, blurry, photorealistic, 3d render, excessive gradients, anti-aliased edges"
)

_LLM_STATE: dict[str, Any] = {"next_try": 0.0, "model": None, "checked": False}


@dataclass
class PromptPlan:
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

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip(" ,.-")


def _translate_phrases(text: str) -> str:
    result = text
    for source in sorted(_PHRASES, key=len, reverse=True):
        if source in result:
            result = result.replace(source, _PHRASES[source])
    return result


def _dedupe_words(text: str) -> str:
    words: list[str] = []
    for word in re.findall(r"[A-Za-z0-9'-]+", text.lower()):
        if word in _STOP_WORDS:
            continue
        if words and words[-1] == word:
            continue
        words.append(word)
    # Remove repeated words anywhere, keeping the first occurrence.
    seen: set[str] = set()
    unique: list[str] = []
    for word in words:
        if word in seen:
            continue
        seen.add(word)
        unique.append(word)
    return " ".join(unique)


def extract_subject(user_prompt: str, mode: str = "icon") -> str:
    text = _translate_phrases(user_prompt.strip())
    # Drop Korean particles/leftovers that the dictionary did not translate.
    text = re.sub(r"[\uac00-\ud7a3]+", " ", text)
    subject = _dedupe_words(text)
    if not subject:
        subject = {
            "icon": "object",
            "character": "character",
            "object": "object",
            "tile": "texture",
        }.get(mode, "object")
    # Keep prompts short enough for CLIP (SDXL chunks long prompts, but short
    # structured prompts produce much more predictable compositions).
    words = subject.split()
    if len(words) > 12:
        subject = " ".join(words[:12])
    return subject


def _subject_with_hint(subject: str) -> str:
    lowered = subject.lower()
    for keyword, hint in _SUBJECT_HINTS.items():
        if keyword in lowered and hint not in lowered:
            return f"{subject} {hint}"
    return subject


def _mode_positive(subject: str, mode: str) -> str:
    if mode == "tile":
        return (
            f"seamless repeating pixel art tile of {subject}, tileable texture, "
            "16-bit game background, clean pixel clusters, limited color palette, "
            "crisp hard pixel edges, top-down view, no text, no labels, no frame"
        )
    if mode == "character":
        return (
            f"pixel art of one single {subject}, full body from head to toe, standing, "
            "centered composition, entire character in frame, game sprite, clear bold "
            "silhouette, simple readable shape, clean edges, limited color palette, "
            "plain pure white background, no scenery, no ground, no shadow, "
            "no other characters or objects"
        )
    if mode == "object":
        return (
            f"pixel art of one single {subject}, one complete object visible, "
            "centered composition, three-quarter view, entire object in frame, "
            "game asset, clear bold silhouette, simple readable shape, clean edges, "
            "limited color palette, plain pure white background, no scenery, "
            "no ground, no shadow, no other objects"
        )
    return (
        f"pixel art of one single {subject}, one complete object visible, centered "
        "composition, front view, entire object in frame, game asset icon, clear bold "
        "silhouette, simple readable shape, clean edges, limited color palette, "
        "plain pure white background, no scenery, no ground, no shadow, no other objects"
    )


def _mode_negative(mode: str, user_negative: str | None, configured: str) -> str:
    specific = {
        "icon": _NEGATIVE_ICON,
        "character": _NEGATIVE_CHARACTER,
        "object": _NEGATIVE_OBJECT,
        "tile": _NEGATIVE_TILE,
    }.get(mode, _NEGATIVE_ICON)
    parts = [str(part).strip() for part in (user_negative, configured) if part and str(part).strip()]
    base = f"{_NEGATIVE_COMMON}, {specific}"
    combined = ", ".join(parts + [base])
    # De-duplicate comma-separated negative terms while preserving order.
    seen: set[str] = set()
    terms: list[str] = []
    for term in combined.split(","):
        clean = _normalize_spaces(term)
        if clean and clean.lower() not in seen:
            seen.add(clean.lower())
            terms.append(clean)
    return ", ".join(terms)


def build_prompt_plan(
    user_prompt: str,
    user_negative: str | None,
    mode: str,
    transparent: bool,
    output_size: int,
    generation,
) -> PromptPlan:
    mode = mode if mode in _MODE_VIEW else "icon"
    subject = extract_subject(user_prompt, mode)
    subject = _subject_with_hint(subject)
    positive = _mode_positive(subject, mode)
    negative = _mode_negative(
        mode,
        user_negative,
        getattr(generation, "negative_prompt", "") or "",
    )
    return PromptPlan(
        asset_type=mode,
        subject=subject,
        view=_MODE_VIEW[mode],
        composition=_MODE_COMPOSITION[mode],
        style="clean 16-bit pixel art, crisp hard pixel edges, limited color palette",
        background="plain pure white background" if mode != "tile" else "seamless texture",
        detail_level="medium, readable at small resolution",
        palette="limited color palette",
        output_resolution=output_size,
        mode=mode,
        source="template",
        positive=positive,
        negative=negative,
    )


def build_prompts(
    user_prompt: str,
    user_negative: str | None,
    mode: str,
    transparent: bool,
    output_size: int,
    generation,
) -> tuple[str, str]:
    plan = build_prompt_plan(
        user_prompt, user_negative, mode, transparent, output_size, generation
    )
    return plan.positive, plan.negative


def _llm_config(generation) -> tuple[bool, str, str, float]:
    enabled = bool(getattr(generation, "prompt_llm_enabled", False))
    base_url = str(getattr(generation, "prompt_llm_url", "http://127.0.0.1:11434")).rstrip("/")
    model = str(getattr(generation, "prompt_llm_model", "") or "")
    timeout = float(getattr(generation, "prompt_llm_timeout_seconds", 4.0) or 4.0)
    return enabled, base_url, model, timeout


async def _query_ollama(user_prompt: str, mode: str, generation) -> str | None:
    """Ask a local Ollama model for a single English subject phrase."""
    enabled, base_url, configured_model, timeout = _llm_config(generation)
    if not enabled:
        return None
    now = time.monotonic()
    if now < _LLM_STATE["next_try"]:
        return None
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client:
            if not _LLM_STATE["checked"]:
                tags = await client.get("/api/tags")
                tags.raise_for_status()
                models = [item.get("name", "") for item in tags.json().get("models", [])]
                models = [item for item in models if item]
                if not models:
                    _LLM_STATE.update(checked=True, next_try=now + 60, model=None)
                    return None
                selected = configured_model if configured_model in models else models[0]
                _LLM_STATE.update(checked=True, model=selected, next_try=0.0)
            model = _LLM_STATE["model"]
            if not model:
                return None
            instruction = (
                "You turn a user's image request into one short English subject phrase "
                "for a single pixel-art game asset. Reply with JSON only: "
                '{"subject": "..."} . The subject must be one object or one character, '
                "never a scene, sprite sheet, or multiple objects. Keep colors/adjectives."
            )
            response = await client.post(
                "/api/generate",
                json={
                    "model": model,
                    "prompt": f"{instruction}\nUser request: {user_prompt}\nMode: {mode}",
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0.1, "num_predict": 120},
                },
            )
            response.raise_for_status()
            payload = response.json()
            data = json.loads(payload.get("response") or "{}")
            subject = str(data.get("subject") or "").strip()
            if 1 <= len(subject) <= 120 and re.search(r"[A-Za-z]", subject):
                logger.info("Local LLM structured prompt subject=%r", subject)
                return subject
    except Exception as exc:
        logger.info("Local LLM prompt structuring unavailable: %s", exc)
        _LLM_STATE.update(checked=True, next_try=now + 300, model=None)
    return None


async def build_prompt_plan_async(
    user_prompt: str,
    user_negative: str | None,
    mode: str,
    transparent: bool,
    output_size: int,
    generation,
) -> PromptPlan:
    plan = build_prompt_plan(
        user_prompt, user_negative, mode, transparent, output_size, generation
    )
    subject = await _query_ollama(user_prompt, mode, generation)
    if not subject:
        return plan
    subject = _subject_with_hint(_dedupe_words(subject)) or plan.subject
    positive = _mode_positive(subject, plan.mode)
    return PromptPlan(
        **{
            **plan.as_dict(),
            "subject": subject,
            "source": "llm",
            "positive": positive,
        }
    )
