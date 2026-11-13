from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import time
import uuid
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import quote

import yaml
from PIL import Image

from app.config import Settings
from app.services.comfy_client import ComfyClient
from app.services.comic import ComicService
from app.services.errors import ComfyExecutionError, PixelForgeError
from app.services.model_notes import checkpoint_recommendation

logger = logging.getLogger("pixelforge.comic_studio")


class ComicStudioError(PixelForgeError):
    code = "COMIC_STUDIO_ERROR"
    status_code = 400


# ---------------------------------------------------------------------------
# Prompt vocabulary
#
# This service intentionally owns its own prompt builder.  It never imports the
# nk comic maker and it never injects a "safe" tag: a local uncensored checkpoint
# receives exactly the tags the author writes.
# ---------------------------------------------------------------------------

SHOT_TAGS = {
    "wide": "wide shot, scenery",
    "full": "full body",
    "knee": "cowboy shot",
    "waist": "upper body",
    "face": "portrait, close-up",
    "detail": "close-up, detail",
    "eyes": "close-up, eyes focus",
    "hands": "close-up, hands focus",
}

ANGLE_TAGS = {
    "eye": "",
    "high": "from above",
    "low": "from below",
    "side": "from side",
    "back": "from behind",
    "tilt": "dutch angle",
}

SHOT_SIZES = {
    "wide": (1344, 768),
    "full": (832, 1216),
    "knee": (1024, 1024),
    "waist": (1024, 1024),
    "face": (896, 1152),
    "detail": (1024, 1024),
    "eyes": (1024, 768),
    "hands": (1024, 768),
}

DEFAULT_STYLE = {
    "pony": "score_9, score_8_up, score_7_up, source_anime",
    "illustrious": "masterpiece, best quality, very aesthetic, absurdres",
    "photo": "masterpiece, best quality, highres, raw photo, photorealistic",
    "generic": "masterpiece, best quality, highres",
}

DEFAULT_NEGATIVE = (
    "worst quality, low quality, lowres, blurry, jpeg artifacts, text, watermark, "
    "signature, username, logo, bad anatomy, bad hands, extra fingers, missing fingers, "
    "extra limbs, deformed, cropped, out of frame"
)

PONY_NEGATIVE = "score_6, score_5, score_4, source_pony, source_furry, source_cartoon"

# Tags that would describe a minor.  Characters in this service must be adults;
# this is the only hard content check.  Everything else is left to the model.
_MINOR_TOKENS = (
    "loli",
    "lolicon",
    "shota",
    "shotacon",
    "child",
    "children",
    "kid",
    "kids",
    "toddler",
    "baby",
    "underage",
    "minor",
    "teen",
    "teenager",
    "elementary school",
    "middle school",
    "little girl",
    "little boy",
    "young girl",
    "young boy",
)

ADULT_WARNING = (
    "성인(18세 이상) 캐릭터만 사용할 수 있습니다. 캐릭터 정의에 adult: true 를 넣고 "
    "미성년자로 해석될 수 있는 태그를 제거해 주세요."
)

# The local user's existing test plan uses this name.  Map it to a generic adult
# appearance so old plans still compile, without carrying a character name into
# the prompt.
CHARACTER_ALIASES = {
    "android_18": "blonde_bob",
}

BUILTIN_CHARACTERS: dict[str, dict[str, Any]] = {
    "blonde_bob": {
        "id": "blonde_bob",
        "name": "금발 보브 · 성인 여성",
        "adult": True,
        "gender": "female",
        "tags": (
            "1girl, adult woman, blonde hair, short hair, bob cut, side part, "
            "blue eyes, fair skin"
        ),
        "default_outfit": (
            "denim vest, striped shirt, black skirt, black leggings, brown boots, "
            "silver hoop earrings"
        ),
        "negative": "long hair, animal ears",
        "description": "짧은 금발 보브와 푸른 눈의 성인 여성. 데님 베스트와 스커트.",
        "builtin": True,
    },
    "brunette_wave": {
        "id": "brunette_wave",
        "name": "갈색 웨이브 · 성인 여성",
        "adult": True,
        "gender": "female",
        "tags": (
            "1girl, adult woman, brunette, long hair, wavy hair, brown eyes, "
            "fair skin, beauty mark"
        ),
        "default_outfit": "white blouse, black pencil skirt, stockings, heels",
        "negative": "",
        "description": "긴 갈색 웨이브 머리의 성인 여성. 블라우스와 펜슬 스커트.",
        "builtin": True,
    },
    "black_hair": {
        "id": "black_hair",
        "name": "흑발 스트레이트 · 성인 여성",
        "adult": True,
        "gender": "female",
        "tags": (
            "1girl, adult woman, black hair, long straight hair, dark eyes, "
            "fair skin, hair ornament"
        ),
        "default_outfit": "black dress, sheer stockings, silver necklace",
        "negative": "",
        "description": "긴 흑발의 성인 여성. 검은 드레스와 은목걸이.",
        "builtin": True,
    },
    "silver_short": {
        "id": "silver_short",
        "name": "은발 숏컷 · 성인 여성",
        "adult": True,
        "gender": "female",
        "tags": (
            "1girl, adult woman, silver hair, short hair, undercut, grey eyes, "
            "pale skin, ear piercing"
        ),
        "default_outfit": "black leather jacket, white tank top, dark jeans",
        "negative": "",
        "description": "은발 숏컷과 회색 눈의 성인 여성. 가죽 재킷.",
        "builtin": True,
    },
    "male_lead": {
        "id": "male_lead",
        "name": "흑발 남성 · 성인",
        "adult": True,
        "gender": "male",
        "tags": (
            "1boy, adult man, black hair, short hair, dark eyes, tall, "
            "broad shoulders, fair skin"
        ),
        "default_outfit": "white shirt, black trousers, wristwatch",
        "negative": "",
        "description": "짧은 흑발의 성인 남성. 셔츠와 슬랙스.",
        "builtin": True,
    },
    "male_rugged": {
        "id": "male_rugged",
        "name": "거친 인상 남성 · 성인",
        "adult": True,
        "gender": "male",
        "tags": (
            "1boy, adult man, dark brown hair, short hair, stubble, amber eyes, "
            "muscular, scars"
        ),
        "default_outfit": "black henley shirt, cargo pants, dog tags",
        "negative": "",
        "description": "수염과 흉터가 있는 성인 남성. 거친 인상.",
        "builtin": True,
    },
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ", ".join(_text(item) for item in value if _text(item))
    return str(value).strip()


def _tag_list(value: Any) -> list[str]:
    """Split prompt tags on commas/newlines while keeping a sentence whole."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        chunks = [_text(item) for item in value]
    else:
        chunks = re.split(r"[,\n]", str(value))
    out: list[str] = []
    seen: set[str] = set()
    for chunk in chunks:
        tag = chunk.strip().strip(",")
        if not tag:
            continue
        key = tag.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(tag)
    return out


def _dedupe_tags(*values: Any) -> str:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        for tag in _tag_list(value):
            key = tag.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(tag)
    return ", ".join(out)


def _model_family(model: str) -> str:
    lowered = (model or "").lower()
    if "pony" in lowered:
        return "pony"
    if any(token in lowered for token in ("noob", "illustrious", "animagine", "anima")):
        return "illustrious"
    if any(
        token in lowered
        for token in ("lustify", "real", "photo", "cyber", "epic", "juggernaut")
    ):
        return "photo"
    return "generic"


def _norm_model(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower().replace(".safetensors", ""))


def _parse_cut_ranges(value: Any) -> set[int] | None:
    """Return None for 'all', or a set of 1-based global cut ids."""
    if value is None:
        return None
    raw = str(value).strip().lower()
    if not raw or raw in {"all", "*"}:
        return None
    ids: set[int] = set()
    for part in re.split(r"[,\s]+", raw):
        if not part:
            continue
        if "-" in part:
            start, _, end = part.partition("-")
            try:
                a, b = int(start), int(end)
            except ValueError:
                continue
            if a > b:
                a, b = b, a
            ids.update(range(max(1, a), min(b, 100000) + 1))
        else:
            try:
                ids.add(int(part))
            except ValueError:
                continue
    return ids


def _assert_adult(text: str) -> None:
    lowered = (text or "").lower()
    for token in _MINOR_TOKENS:
        if " " in token:
            if token in lowered:
                raise ComicStudioError(ADULT_WARNING)
        elif re.search(rf"\b{re.escape(token)}\b", lowered):
            raise ComicStudioError(ADULT_WARNING)


def _rewrite_plan_model(raw: str, model: str) -> str:
    """Point the plan's top-level model/flow key at the chosen checkpoint.

    The toolbar model picker is the primary control, so saving a new model should
    not be silently overridden by an old ``model:`` line inside plan.yaml.
    """
    if not model or not raw:
        return raw
    lines = raw.splitlines()
    for index, line in enumerate(lines):
        match = re.match(r"^(model|flow)\s*:\s*(.*)$", line)
        if not match:
            continue
        lines[index] = f"{match.group(1)}: {json.dumps(model, ensure_ascii=False)}"
        text = "\n".join(lines)
        return text + ("\n" if raw.endswith("\n") else "")
    return raw


class ComicStudioService:
    """An independent, uncensored comic workflow for PixelForge.

    The data model is deliberately small:

      output/comic_studio/projects/<project>/
        project.json          project + plan + candidate/pick state
        cuts/<p1c1>/          generated candidates and their sidecars
        exports/              combined PDF

    Prompt construction, YAML compilation, candidate rendering and page
    assembly all live here.  The nk comic maker is not imported or copied.
    """

    def __init__(self, settings: Settings, comfy: ComfyClient, comic: ComicService):
        self.settings = settings
        self.comfy = comfy
        self.comic = comic
        self._generation_lock = asyncio.Lock()
        self._id_re = re.compile(r"^[A-Za-z0-9_.-]{2,90}$")
        self._cut_key_re = re.compile(r"^[A-Za-z0-9_.-]{1,60}$")
        self._candidate_re = re.compile(r"^[A-Za-z0-9_.-]+\.(?:png|jpg|jpeg|webp)$", re.I)

    # ------------------------------------------------------------------ paths
    @property
    def root_dir(self) -> Path:
        return self.settings.resolve(self.settings.comic_studio.root_dir)

    @property
    def projects_dir(self) -> Path:
        return self.root_dir / "projects"

    @property
    def characters_dir(self) -> Path:
        return self.root_dir / "characters"

    def ensure_dirs(self) -> None:
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        self.characters_dir.mkdir(parents=True, exist_ok=True)

    def _project_dir(self, project_id: str) -> Path:
        if not self._id_re.fullmatch(project_id or ""):
            raise ComicStudioError("잘못된 프로젝트 ID입니다.")
        return self.projects_dir / project_id

    def _project_file(self, project_id: str) -> Path:
        return self._project_dir(project_id) / "project.json"

    def _load_project(self, project_id: str) -> dict[str, Any]:
        path = self._project_file(project_id)
        if not path.is_file():
            raise ComicStudioError("프로젝트를 찾을 수 없습니다.")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ComicStudioError("프로젝트 파일을 읽을 수 없습니다.", detail=str(exc)) from exc
        if not isinstance(data, dict):
            raise ComicStudioError("프로젝트 파일 형식이 올바르지 않습니다.")
        return data

    def _save_project(self, project: dict[str, Any]) -> None:
        project["updated_at"] = _now_iso()
        directory = self._project_dir(str(project["id"]))
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "project.json"
        temp = directory / "project.json.tmp"
        temp.write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)

    # --------------------------------------------------------------- characters
    def _load_custom_character(self, character_id: str) -> dict[str, Any] | None:
        if not self._id_re.fullmatch(character_id or ""):
            return None
        path = self.characters_dir / f"{character_id}.yaml"
        if not path.is_file():
            return None
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            return None
        if not isinstance(data, dict):
            return None
        data.setdefault("id", character_id)
        data["builtin"] = False
        return data

    def list_characters(self) -> list[dict[str, Any]]:
        self.ensure_dirs()
        items: list[dict[str, Any]] = [dict(item) for item in BUILTIN_CHARACTERS.values()]
        for path in sorted(self.characters_dir.glob("*.yaml")):
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except (OSError, yaml.YAMLError):
                continue
            if not isinstance(data, dict):
                continue
            data.setdefault("id", path.stem)
            data["builtin"] = False
            items.append(data)
        return items

    def _character(self, character_id: str) -> dict[str, Any] | None:
        key = (character_id or "").strip()
        if not key:
            return None
        if key in BUILTIN_CHARACTERS:
            return dict(BUILTIN_CHARACTERS[key])
        alias = CHARACTER_ALIASES.get(key.lower())
        if alias and alias in BUILTIN_CHARACTERS:
            return dict(BUILTIN_CHARACTERS[alias])
        return self._load_custom_character(key)

    def save_character(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.ensure_dirs()
        character_id = str(payload.get("id") or "").strip()
        if not self._id_re.fullmatch(character_id):
            raise ComicStudioError("캐릭터 ID는 영문·숫자·._- 2~90자로 입력해 주세요.")
        if character_id in BUILTIN_CHARACTERS:
            raise ComicStudioError("내장 캐릭터 ID는 덮어쓸 수 없습니다. 새 ID를 써 주세요.")
        if not bool(payload.get("adult")):
            raise ComicStudioError(ADULT_WARNING)
        tags = _text(payload.get("tags"))
        if not tags:
            raise ComicStudioError("캐릭터 외형 태그를 입력해 주세요.")
        _assert_adult(tags)
        data = {
            "id": character_id,
            "name": _text(payload.get("name")) or character_id,
            "adult": True,
            "gender": _text(payload.get("gender")) or "female",
            "tags": tags,
            "default_outfit": _text(payload.get("default_outfit")),
            "negative": _text(payload.get("negative")),
            "description": _text(payload.get("description")),
        }
        path = self.characters_dir / f"{character_id}.yaml"
        path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
        return {**data, "builtin": False}

    def delete_character(self, character_id: str) -> dict[str, Any]:
        if character_id in BUILTIN_CHARACTERS:
            raise ComicStudioError("내장 캐릭터는 삭제할 수 없습니다.")
        path = self.characters_dir / f"{character_id}.yaml"
        if not path.is_file():
            raise ComicStudioError("캐릭터를 찾을 수 없습니다.")
        path.unlink()
        return {"id": character_id, "deleted": True}

    # ---------------------------------------------------------------- projects
    def _starter_plan(self, title: str, model: str) -> str:
        title_yaml = json.dumps(title, ensure_ascii=False)
        model_yaml = json.dumps(model, ensure_ascii=False)
        return f"""# PixelForge 만화 스튜디오 콘티
# - who: [] 이면 사람 없는 배경 컷, who: [hero] 이면 캐릭터 컷
# - cast: 짧은 이름 -> 캐릭터 ID (내장: {", ".join(BUILTIN_CHARACTERS)})
# - outfit: 아래 outfits 의 이름 또는 직접 쓴 태그
# - 이 파일에는 safe 태그를 자동으로 넣지 않습니다. 모델에 그대로 전달됩니다.
title: {title_yaml}
model: {model_yaml}
style: ""              # 비우면 모델 계열 기본 화풍
negative: ""           # 비우면 기본 네거티브
rating: ""             # 필요할 때만: explicit / questionable / safe
locations:
  room: "bedroom, bed, window, curtains, night, indoors"
outfits:
  casual: "white shirt, black skirt"
cast: {{hero: blonde_bob}}
pages:
  - note: "1페이지 — 도입"
    cuts:
      - who: []
        shot: wide
        loc: room
        action: "night, window, city lights, dim light"
        text: "고요한 밤."
        position: top
      - who: [hero]
        shot: full
        angle: eye
        loc: room
        outfit: casual
        action: "standing, looking at viewer, arms at sides"
        text: ""
      - who: [hero]
        shot: face
        angle: eye
        loc: room
        action: "looking at viewer, soft smile"
        text: "…아직 안 자?"
        position: bottom
"""

    def create_project(self, title: str, model: str = "", plan_yaml: str | None = None) -> dict[str, Any]:
        self.ensure_dirs()
        clean_title = _text(title) or "새 만화"
        chosen_model = _text(model) or self.settings.comic_studio.default_model
        project_id = (
            "p_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:5]
        )
        project = {
            "version": 1,
            "id": project_id,
            "title": clean_title,
            "model": chosen_model,
            "plan_yaml": plan_yaml if isinstance(plan_yaml, str) and plan_yaml.strip() else self._starter_plan(clean_title, chosen_model),
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "cuts": {},
            "pages": [],
        }
        self._save_project(project)
        return self.project_detail(project_id)

    def list_projects(self) -> list[dict[str, Any]]:
        self.ensure_dirs()
        items: list[dict[str, Any]] = []
        for path in self.projects_dir.glob("*/project.json"):
            try:
                project = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(project, dict):
                continue
            try:
                compiled, _warnings, error = self._compile_plan(project)
            except ComicStudioError as exc:
                compiled, error = {}, exc.message
            cuts = compiled.get("cuts") if compiled else []
            states = project.get("cuts") if isinstance(project.get("cuts"), dict) else {}
            candidate_count = 0
            picked_count = 0
            cover_url: str | None = None
            for cut in cuts or []:
                state = states.get(cut["key"]) if isinstance(states, dict) else None
                if not isinstance(state, dict):
                    continue
                names = self._state_candidate_names(state)
                candidate_count += len(names)
                selected = state.get("selected")
                if selected and selected in names:
                    picked_count += 1
                    if cover_url is None:
                        cover_url = self._file_url(str(project.get("id")), f"cuts/{cut['key']}/{selected}")
                elif cover_url is None and names:
                    cover_url = self._file_url(str(project.get("id")), f"cuts/{cut['key']}/{names[0]}")
            items.append(
                {
                    "id": str(project.get("id")),
                    "title": str(project.get("title") or ""),
                    "model": str(compiled.get("model") if compiled else project.get("model") or ""),
                    "cut_count": len(cuts or []),
                    "candidate_count": candidate_count,
                    "picked_count": picked_count,
                    "page_count": len(project.get("pages") or []),
                    "updated_at": project.get("updated_at"),
                    "cover_url": cover_url,
                    "error": error,
                }
            )
        items.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
        return items

    def update_project(self, project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        project = self._load_project(project_id)
        model_changed = False
        if "title" in payload and payload["title"] is not None:
            title = _text(payload.get("title"))
            if title:
                project["title"] = title
        if "model" in payload and payload["model"] is not None:
            model = _text(payload.get("model"))
            if model and model != project.get("model"):
                project["model"] = model
                model_changed = True
        if "plan_yaml" in payload and payload["plan_yaml"] is not None:
            project["plan_yaml"] = str(payload.get("plan_yaml"))
        if model_changed:
            project["plan_yaml"] = _rewrite_plan_model(
                str(project.get("plan_yaml") or ""), str(project["model"])
            )
        self._save_project(project)
        return self.project_detail(project_id)

    def delete_project(self, project_id: str) -> dict[str, Any]:
        directory = self._project_dir(project_id)
        if not directory.is_dir():
            raise ComicStudioError("프로젝트를 찾을 수 없습니다.")
        # Page files live in the shared comic_pages folder; remove the ones this
        # project owns before deleting the project directory.
        try:
            project = self._load_project(project_id)
            for page in project.get("pages") or []:
                page_id = str(page.get("id") or "")
                if page_id:
                    self.comic.delete_page(page_id)
        except Exception:
            logger.debug("Could not clean project pages", exc_info=True)
        import shutil

        shutil.rmtree(directory, ignore_errors=True)
        return {"id": project_id, "deleted": True}

    # -------------------------------------------------------------- compilation
    def compile_project(self, project_id: str) -> dict[str, Any]:
        project = self._load_project(project_id)
        compiled, warnings, error = self._compile_plan(project)
        if error:
            raise ComicStudioError(f"콘티를 컴파일할 수 없습니다. {error}")
        return {
            "id": project_id,
            "warnings": warnings,
            "cuts": len(compiled.get("cuts") or []),
            "pages": len(compiled.get("pages") or []),
            "model": compiled.get("model"),
        }

    def project_detail(self, project_id: str) -> dict[str, Any]:
        project = self._load_project(project_id)
        try:
            compiled, warnings, error = self._compile_plan(project)
        except ComicStudioError as exc:
            compiled, warnings, error = {}, [], exc.message
        cuts: list[dict[str, Any]] = []
        states = project.get("cuts") if isinstance(project.get("cuts"), dict) else {}
        for cut in (compiled.get("cuts") if compiled else []) or []:
            state = states.get(cut["key"]) if isinstance(states, dict) else None
            cuts.append(self._cut_view(project_id, cut, state if isinstance(state, dict) else {}))
        pages = []
        for page in project.get("pages") or []:
            if not isinstance(page, dict):
                continue
            page_id = str(page.get("id") or "")
            pages.append(
                {
                    **page,
                    "image_url": page.get("image_url") or f"/files/comic_pages/page_{page_id}.png",
                    "pdf_url": page.get("pdf_url") or f"/api/comic/page/{page_id}.pdf",
                }
            )
        pages.sort(key=lambda item: int(item.get("number") or 0))
        return {
            "id": str(project.get("id")),
            "title": str(project.get("title") or ""),
            "model": str(compiled.get("model") if compiled else project.get("model") or ""),
            "plan_yaml": str(project.get("plan_yaml") or ""),
            "created_at": project.get("created_at"),
            "updated_at": project.get("updated_at"),
            "cuts": cuts,
            "pages": pages,
            "plan_pages": (compiled.get("pages") if compiled else []) or [],
            "warnings": warnings,
            "error": error,
            "compiled": {
                "title": compiled.get("title") if compiled else project.get("title"),
                "style": compiled.get("style") if compiled else "",
                "negative": compiled.get("negative") if compiled else "",
                "rating": compiled.get("rating") if compiled else "",
                "page_count": len(compiled.get("pages") or []) if compiled else 0,
                "cut_count": len(compiled.get("cuts") or []) if compiled else 0,
            },
            "characters": self.list_characters(),
        }

    def _resolve_character_value(
        self,
        short_name: str,
        value: Any,
        warnings: list[str],
    ) -> dict[str, Any] | None:
        if isinstance(value, dict):
            character_id = _text(value.get("character") or value.get("id"))
            base = self._character(character_id) if character_id else None
            tags = _text(
                value.get("tags")
                or value.get("tags_full")
                or value.get("tags_short")
                or value.get("appearance")
            )
            adult = value.get("adult")
            if base:
                merged = dict(base)
                if tags:
                    merged["tags"] = tags
                if value.get("default_outfit") is not None:
                    merged["default_outfit"] = _text(value.get("default_outfit"))
                if value.get("negative") is not None:
                    merged["negative"] = _text(value.get("negative"))
                if value.get("gender"):
                    merged["gender"] = _text(value.get("gender"))
                return merged
            if adult is not True:
                raise ComicStudioError(f"{short_name}: " + ADULT_WARNING)
            if not tags:
                warnings.append(f"{short_name}: 캐릭터 외형 태그가 없습니다.")
                return None
            _assert_adult(tags)
            return {
                "id": _text(value.get("id")) or short_name,
                "name": _text(value.get("name")) or short_name,
                "adult": True,
                "gender": _text(value.get("gender")) or "female",
                "tags": tags,
                "default_outfit": _text(value.get("default_outfit")),
                "negative": _text(value.get("negative")),
                "trigger": _text(value.get("trigger")),
                "builtin": False,
            }
        raw = _text(value)
        if not raw:
            return None
        found = self._character(raw)
        if found:
            if found.get("adult") is not True:
                raise ComicStudioError(f"{raw}: " + ADULT_WARNING)
            return found
        if "," in raw or " " in raw:
            _assert_adult(raw)
            return {
                "id": short_name,
                "name": short_name,
                "adult": True,
                "gender": "female",
                "tags": raw,
                "default_outfit": "",
                "negative": "",
                "trigger": "",
                "builtin": False,
            }
        warnings.append(
            f"{short_name}: '{raw}' 캐릭터를 찾지 못했습니다. "
            "내장 캐릭터 ID를 쓰거나 characters: 아래에 외형 태그를 직접 넣어 주세요."
        )
        return None

    def _compile_plan(self, project: dict[str, Any]) -> tuple[dict[str, Any], list[str], str | None]:
        warnings: list[str] = []
        raw = str(project.get("plan_yaml") or "")
        try:
            plan = yaml.safe_load(raw) if raw.strip() else None
        except yaml.YAMLError as exc:
            return {}, warnings, f"YAML 오류: {exc}"
        if not isinstance(plan, dict):
            return {}, warnings, "plan.yaml 의 최상위가 매핑(dict)이 아닙니다."
        pages_raw = plan.get("pages")
        if not isinstance(pages_raw, list) or not pages_raw:
            return {}, warnings, "pages: 아래에 페이지를 하나 이상 넣어 주세요."

        model = _text(plan.get("model") or plan.get("flow") or project.get("model"))
        if not model:
            warnings.append("모델이 비어 있습니다. 프로젝트 설정에서 체크포인트를 골라 주세요.")
        family = _model_family(model)
        style = _text(plan.get("style")) or DEFAULT_STYLE[family]
        negative = _text(plan.get("negative")) or DEFAULT_NEGATIVE
        if family == "pony":
            negative = _dedupe_tags(negative, PONY_NEGATIVE)
        rating = _text(plan.get("rating"))
        artist = _text(plan.get("artist"))
        extra = _text(plan.get("extra"))
        locations = plan.get("locations") if isinstance(plan.get("locations"), dict) else {}
        outfits = plan.get("outfits") if isinstance(plan.get("outfits"), dict) else {}
        cast = plan.get("cast") if isinstance(plan.get("cast"), dict) else {}
        inline_chars = plan.get("characters") if isinstance(plan.get("characters"), dict) else {}
        default_width, default_height = self.settings.comic_studio.default_cut_size
        plan_has_size = plan.get("width") is not None or plan.get("height") is not None
        plan_width = self._safe_int(plan.get("width"), default_width, 256, 2048)
        plan_height = self._safe_int(plan.get("height"), default_height, 256, 2048)
        plan_steps = self._safe_int(plan.get("steps"), 0, 0, 150)
        plan_cfg = self._safe_float(plan.get("cfg"), 0.0, 0.0, 30.0)
        plan_sampler = _text(plan.get("sampler"))
        plan_scheduler = _text(plan.get("scheduler"))

        resolved_chars: dict[str, dict[str, Any] | None] = {}
        for name, value in cast.items():
            resolved_chars[str(name)] = self._resolve_character_value(str(name), value, warnings)
        for name, value in inline_chars.items():
            resolved_chars[str(name)] = self._resolve_character_value(str(name), value, warnings)

        cuts: list[dict[str, Any]] = []
        pages: list[dict[str, Any]] = []
        global_id = 0
        for page_index, page in enumerate(pages_raw, start=1):
            if not isinstance(page, dict):
                warnings.append(f"{page_index}페이지가 매핑이 아니어서 건너뜁니다.")
                continue
            raw_cuts = page.get("cuts")
            if not isinstance(raw_cuts, list) or not raw_cuts:
                warnings.append(f"{page_index}페이지에 cuts 가 없습니다.")
                continue
            page_cut_ids: list[int] = []
            for cut_index, cut in enumerate(raw_cuts, start=1):
                global_id += 1
                cut_id = global_id
                key = f"p{page_index}c{cut_index}"
                if not isinstance(cut, dict):
                    warnings.append(f"{cut_id}번 컷이 매핑이 아니어서 건너뜁니다.")
                    continue
                who_raw = cut.get("who")
                if isinstance(who_raw, str):
                    who = [part.strip() for part in who_raw.split(",") if part.strip()]
                elif isinstance(who_raw, (list, tuple)):
                    who = [str(part).strip() for part in who_raw if str(part).strip()]
                else:
                    who = []
                characters: list[dict[str, Any]] = []
                for name in who:
                    character = resolved_chars.get(name)
                    if character is None and name not in resolved_chars:
                        warnings.append(f"{cut_id}번 컷: who '{name}' 가 cast/characters 에 없습니다.")
                    if character:
                        characters.append(character)

                shot = _text(cut.get("shot")).lower() or "full"
                if shot not in SHOT_TAGS:
                    warnings.append(f"{cut_id}번 컷: shot '{shot}' 를 full 로 바꿉니다.")
                    shot = "full"
                angle = _text(cut.get("angle")).lower() or "eye"
                if angle not in ANGLE_TAGS:
                    warnings.append(f"{cut_id}번 컷: angle '{angle}' 를 eye 로 바꿉니다.")
                    angle = "eye"
                loc_key = _text(cut.get("loc"))
                loc_tags = _text(locations.get(loc_key)) if loc_key else ""
                if loc_key and loc_key not in locations:
                    warnings.append(f"{cut_id}번 컷: 장소 '{loc_key}' 가 locations 에 없습니다.")
                    loc_tags = loc_key if "," in loc_key else ""
                background = _text(cut.get("bg") or cut.get("background"))
                if background:
                    loc_tags = (
                        "simple background"
                        if background.lower() in {"simple", "white", "none"}
                        else background
                    )

                action = _text(cut.get("action") or cut.get("tags") or cut.get("pose"))
                lowered_action = action.lower()
                if (
                    any(
                        token in lowered_action
                        for token in ("sex", "penetration", "fellatio", "paizuri", "vaginal")
                    )
                    and len(characters) < 2
                ):
                    warnings.append(
                        f"{cut_id}번 컷: 성행위 태그는 상대가 있는 두 명 컷(who: [a, b])에서 더 잘 동작합니다."
                    )
                scene = _text(cut.get("scene") or cut.get("sentence"))
                outfit = self._outfit_tags(cut, outfits)
                global_wear = self._global_wear_tags(plan, cut_id, who, outfits)
                text = self._cut_text(cut)
                position = _text(cut.get("position")).lower() or "top"
                if position not in {"top", "bottom", "none"}:
                    position = "top"
                if plan_has_size:
                    base_width, base_height = plan_width, plan_height
                else:
                    base_width, base_height = SHOT_SIZES.get(shot, (plan_width, plan_height))
                width = self._safe_int(cut.get("width"), base_width, 256, 2048)
                height = self._safe_int(cut.get("height"), base_height, 256, 2048)
                if (
                    cut.get("width") is None
                    and cut.get("height") is None
                    and len(characters) > 1
                    and shot in {"full", "knee", "waist"}
                ):
                    width, height = 1216, 832

                prompt = self._build_prompt(
                    style=style,
                    rating=rating,
                    artist=artist,
                    characters=characters,
                    action=action,
                    scene=scene,
                    shot=shot,
                    angle=angle,
                    loc_tags=loc_tags,
                    outfit=outfit,
                    global_wear=global_wear,
                    extra=_dedupe_tags(extra, _text(cut.get("extra"))),
                )
                cut_negative = _dedupe_tags(
                    negative,
                    *(character.get("negative", "") for character in characters),
                    _text(cut.get("negative")),
                )
                _assert_adult(" ".join([action, outfit, global_wear]))
                cuts.append(
                    {
                        "id": cut_id,
                        "key": key,
                        "page": page_index,
                        "index": cut_index,
                        "shot": shot,
                        "angle": angle,
                        "loc": loc_key,
                        "who": who,
                        "characters": [str(character.get("id") or character.get("name") or "") for character in characters],
                        "action": action,
                        "scene": scene,
                        "text": text,
                        "position": position,
                        "width": width,
                        "height": height,
                        "prompt": prompt,
                        "negative": cut_negative,
                        "steps": self._safe_int(cut.get("steps"), plan_steps, 0, 150),
                        "cfg": self._safe_float(cut.get("cfg"), plan_cfg, 0.0, 30.0),
                        "sampler": _text(cut.get("sampler")) or plan_sampler,
                        "scheduler": _text(cut.get("scheduler")) or plan_scheduler,
                    }
                )
                page_cut_ids.append(cut_id)
            pages.append(
                {
                    "number": page_index,
                    "note": _text(page.get("note")),
                    "cut_ids": page_cut_ids,
                }
            )
        cut_ids = {int(cut["id"]) for cut in cuts}
        for key in ("wear", "state"):
            entries = plan.get(key)
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                allowed = _parse_cut_ranges(entry.get("cuts"))
                if allowed is not None and not (allowed & cut_ids):
                    warnings.append(
                        f"{key} cuts '{_text(entry.get('cuts'))}' 범위가 이 콘티의 컷 번호"
                        f"({min(cut_ids) if cut_ids else 0}-{max(cut_ids) if cut_ids else 0})와 겹치지 않습니다."
                    )
        if not cuts:
            warnings.append("컴파일된 컷이 없습니다. pages -> cuts 를 확인해 주세요.")
        return (
            {
                "title": _text(plan.get("title")) or str(project.get("title") or ""),
                "model": model,
                "style": style,
                "negative": negative,
                "rating": rating,
                "cuts": cuts,
                "pages": pages,
            },
            warnings,
            None,
        )

    # ------------------------------------------------------------ prompt helpers
    @staticmethod
    def _safe_int(value: Any, fallback: int, minimum: int, maximum: int) -> int:
        try:
            number = int(value)
        except (TypeError, ValueError):
            return max(minimum, min(maximum, int(fallback)))
        return max(minimum, min(maximum, number))

    @staticmethod
    def _safe_float(value: Any, fallback: float, minimum: float, maximum: float) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return max(minimum, min(maximum, float(fallback)))
        return max(minimum, min(maximum, number))

    @staticmethod
    def _cut_text(cut: dict[str, Any]) -> str:
        explicit = _text(cut.get("text") or cut.get("caption"))
        if explicit:
            return explicit
        lines = cut.get("lines")
        if isinstance(lines, (list, tuple)):
            texts = []
            for line in lines:
                if isinstance(line, dict):
                    value = _text(line.get("text"))
                else:
                    value = _text(line)
                if value:
                    texts.append(value)
            return "\n".join(texts)
        return _text(lines)

    @staticmethod
    def _outfit_tags(cut: dict[str, Any], outfits: dict[str, Any]) -> str:
        value = cut.get("outfit") or cut.get("wear") or cut.get("clothes")
        if isinstance(value, dict):
            return _text(value.get("tags"))
        raw = _text(value)
        if raw and raw in outfits:
            entry = outfits[raw]
            if isinstance(entry, dict):
                return _text(entry.get("tags"))
            return _text(entry)
        return raw

    def _global_wear_tags(
        self,
        plan: dict[str, Any],
        cut_id: int,
        who: list[str],
        outfits: dict[str, Any],
    ) -> str:
        chunks: list[str] = []
        for key in ("wear", "state"):
            entries = plan.get(key)
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                allowed = _parse_cut_ranges(entry.get("cuts"))
                if allowed is not None and cut_id not in allowed:
                    continue
                entry_who = _text(entry.get("who"))
                if entry_who and entry_who not in who:
                    continue
                value = entry.get("tags")
                if isinstance(value, dict):
                    chunks.append(_text(value.get("tags")))
                elif isinstance(value, str) and value in outfits:
                    outfit = outfits[value]
                    chunks.append(_text(outfit.get("tags") if isinstance(outfit, dict) else outfit))
                else:
                    chunks.append(_text(value))
        return _dedupe_tags(*chunks)

    def _build_prompt(
        self,
        *,
        style: str,
        rating: str,
        artist: str,
        characters: list[dict[str, Any]],
        action: str,
        scene: str,
        shot: str,
        angle: str,
        loc_tags: str,
        outfit: str,
        global_wear: str,
        extra: str,
    ) -> str:
        tags: list[str] = [style]
        if rating:
            tags.append(rating)
        if artist:
            tags.append(f"by {artist}")
        if characters:
            tags.extend(self._character_tags(characters, include_outfit=not (outfit or global_wear)))
        else:
            tags.append("no humans")
        if action:
            tags.append(action)
        if characters:
            shot_tag = SHOT_TAGS.get(shot, "")
        elif shot in {"wide", "full"}:
            shot_tag = "scenery, wide shot"
        elif shot in {"face", "detail", "eyes", "hands"}:
            shot_tag = "close-up, object focus"
        else:
            shot_tag = "scenery"
        if shot_tag:
            tags.append(shot_tag)
        angle_tag = ANGLE_TAGS.get(angle, "")
        if angle_tag:
            tags.append(angle_tag)
        if loc_tags:
            tags.append(loc_tags)
        if outfit:
            tags.append(outfit)
        if global_wear:
            tags.append(global_wear)
        if extra:
            tags.append(extra)
        prompt = _dedupe_tags(*tags)
        if scene:
            prompt = f"{prompt}, {scene}" if prompt else scene
        return prompt

    @staticmethod
    def _character_tags(characters: list[dict[str, Any]], *, include_outfit: bool = True) -> list[str]:
        if len(characters) == 1:
            character = characters[0]
            return [
                _text(character.get("trigger")),
                _text(character.get("tags")),
                _text(character.get("default_outfit")) if include_outfit else "",
            ]
        gender_counts = {"female": 0, "male": 0}
        for character in characters:
            gender = _text(character.get("gender")).lower()
            if gender in gender_counts:
                gender_counts[gender] += 1
        if gender_counts["male"] == 0:
            count_tag = f"{len(characters)}girls"
        elif gender_counts["female"] == 0:
            count_tag = f"{len(characters)}boys"
        else:
            count_tag = f"{gender_counts['female']}girls, {gender_counts['male']}boys"
        drop = {
            "1girl",
            "1boy",
            "2girls",
            "2boys",
            "multiple girls",
            "multiple boys",
            "solo",
        }
        tags = [count_tag]
        for character in characters:
            cleaned = ", ".join(
                tag for tag in _tag_list(character.get("tags")) if tag.lower() not in drop
            )
            tags.append(cleaned)
            if include_outfit:
                tags.append(_text(character.get("default_outfit")))
        return tags

    # ------------------------------------------------------------- cut state
    @staticmethod
    def _state_candidate_names(state: dict[str, Any]) -> list[str]:
        names: list[str] = []
        for item in state.get("candidates") or []:
            if isinstance(item, str):
                names.append(item)
            elif isinstance(item, dict):
                name = _text(item.get("name"))
                if name:
                    names.append(name)
        return names

    def _cut_dir(self, project_id: str, cut_key: str) -> Path:
        if not self._cut_key_re.fullmatch(cut_key or ""):
            raise ComicStudioError("잘못된 컷 키입니다.")
        return self._project_dir(project_id) / "cuts" / cut_key

    def _file_url(self, project_id: str, relative: str) -> str:
        return f"/api/comic-studio/projects/{quote(project_id)}/file/{quote(relative, safe='/')}"

    def _candidate_path(self, project_id: str, cut_key: str, name: str) -> Path:
        if not self._candidate_re.fullmatch(name or ""):
            raise ComicStudioError("잘못된 후보 파일 이름입니다.")
        path = (self._cut_dir(project_id, cut_key) / name).resolve()
        directory = self._cut_dir(project_id, cut_key).resolve()
        if directory != path.parent:
            raise ComicStudioError("허용되지 않은 후보 경로입니다.")
        return path

    def _cut_view(self, project_id: str, cut: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        candidates = []
        for item in state.get("candidates") or []:
            if isinstance(item, str):
                item = {"name": item}
            if not isinstance(item, dict):
                continue
            name = _text(item.get("name"))
            if not name:
                continue
            try:
                path = self._candidate_path(project_id, cut["key"], name)
            except ComicStudioError:
                continue
            if not path.is_file():
                continue
            candidates.append(
                {
                    **item,
                    "name": name,
                    "url": self._file_url(project_id, f"cuts/{cut['key']}/{name}"),
                }
            )
        selected = _text(state.get("selected"))
        selected_url = None
        if selected:
            try:
                path = self._candidate_path(project_id, cut["key"], selected)
                if path.is_file():
                    selected_url = self._file_url(project_id, f"cuts/{cut['key']}/{selected}")
            except ComicStudioError:
                selected = ""
        return {
            **cut,
            "candidates": candidates,
            "selected": selected or None,
            "selected_url": selected_url,
        }

    def _find_cut(self, compiled: dict[str, Any], cut_id: int | str) -> dict[str, Any]:
        raw = str(cut_id)
        for cut in compiled.get("cuts") or []:
            if raw in {str(cut.get("id")), str(cut.get("key"))}:
                return cut
        raise ComicStudioError(f"{raw}번 컷을 찾을 수 없습니다. 먼저 콘티를 컴파일해 주세요.")

    # -------------------------------------------------------------- generation
    async def _resolve_checkpoint(self, requested: str) -> str:
        checkpoints, _ = await self.comfy.get_available_models()
        name = _text(requested)
        if name in checkpoints:
            return name
        normalized = _norm_model(name)
        matches = [item for item in checkpoints if _norm_model(item) == normalized]
        if not matches and normalized:
            matches = [
                item
                for item in checkpoints
                if normalized in _norm_model(item) or _norm_model(item) in normalized
            ]
        if matches:
            return sorted(matches, key=len)[0]
        sample = ", ".join(sorted(checkpoints)[:8])
        raise ComicStudioError(
            f"체크포인트를 찾을 수 없습니다: {name or '(비어 있음)'}. "
            f"ComfyUI 체크포인트 예: {sample}"
        )

    def _build_workflow(
        self,
        *,
        model: str,
        prompt: str,
        negative: str,
        width: int,
        height: int,
        steps: int,
        cfg: float,
        seed: int,
        sampler: str,
        scheduler: str,
        prefix: str,
    ) -> dict[str, Any]:
        return {
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": model},
            },
            "2": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": prompt, "clip": ["1", 1]},
            },
            "3": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": negative, "clip": ["1", 1]},
            },
            "4": {
                "class_type": "EmptyLatentImage",
                "inputs": {"width": width, "height": height, "batch_size": 1},
            },
            "5": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": seed,
                    "steps": steps,
                    "cfg": cfg,
                    "sampler_name": sampler,
                    "scheduler": scheduler,
                    "denoise": 1.0,
                    "model": ["1", 0],
                    "positive": ["2", 0],
                    "negative": ["3", 0],
                    "latent_image": ["4", 0],
                },
            },
            "6": {
                "class_type": "VAEDecode",
                "inputs": {"samples": ["5", 0], "vae": ["1", 2]},
            },
            "7": {
                "class_type": "SaveImage",
                "inputs": {"filename_prefix": prefix, "images": ["6", 0]},
            },
        }

    @staticmethod
    def _entry_images(entry: dict[str, Any]) -> list[dict[str, Any]]:
        images: list[dict[str, Any]] = []
        for node in (entry.get("outputs") or {}).values():
            if not isinstance(node, dict):
                continue
            for image in node.get("images") or []:
                if isinstance(image, dict) and image.get("filename"):
                    images.append(image)
        return images

    async def _render_one(
        self,
        *,
        workflow: dict[str, Any],
        timeout: int,
    ) -> tuple[bytes, float]:
        prompt_id = await self.comfy.queue_prompt(
            workflow, client_id=f"pixelforge-comic-{uuid.uuid4().hex}"
        )
        started = time.monotonic()
        deadline = started + max(60, timeout)
        while time.monotonic() < deadline:
            entry = await self.comfy.get_history(prompt_id)
            if entry:
                images = self._entry_images(entry)
                if images:
                    image = images[0]
                    data = await self.comfy.view_image(
                        str(image.get("filename") or ""),
                        str(image.get("subfolder") or ""),
                        str(image.get("type") or "output"),
                    )
                    return data, time.monotonic() - started
                status = entry.get("status") or {}
                if status.get("status_str") in {"success", "error"} or status.get("completed"):
                    message, code = ComfyClient.extract_execution_error(entry)
                    raise ComfyExecutionError(message, code=code)
            await asyncio.sleep(0.6)
        raise ComfyExecutionError(
            "ComfyUI 생성 시간이 초과되었습니다. 모델·VRAM 상태를 확인하거나 스텝/해상도를 낮춰 주세요."
        )

    def _next_candidate_name(self, project_id: str, cut_key: str, seed: int) -> tuple[str, int]:
        directory = self._cut_dir(project_id, cut_key)
        directory.mkdir(parents=True, exist_ok=True)
        highest = 0
        for path in directory.glob("cand_*.png"):
            match = re.match(r"cand_(\d+)", path.name)
            if match:
                highest = max(highest, int(match.group(1)))
        index = highest + 1
        return f"cand_{index:03d}_s{seed}.png", index

    def _save_candidate(
        self,
        *,
        project_id: str,
        cut_key: str,
        data: bytes,
        seed: int,
        model: str,
        steps: int,
        cfg: float,
        width: int,
        height: int,
        prompt: str,
        negative: str,
        sampler: str,
        scheduler: str,
        elapsed: float,
    ) -> dict[str, Any]:
        name, index = self._next_candidate_name(project_id, cut_key, seed)
        path = self._candidate_path(project_id, cut_key, name)
        path.write_bytes(data)
        try:
            with Image.open(BytesIO(data)) as image:
                actual_width, actual_height = image.size
                image_format = image.format or "PNG"
        except Exception:
            actual_width, actual_height = width, height
            image_format = "PNG"
        item = {
            "name": name,
            "index": index,
            "seed": seed,
            "model": model,
            "steps": steps,
            "cfg": cfg,
            "width": actual_width,
            "height": actual_height,
            "format": image_format,
            "elapsed": round(elapsed, 2),
            "created_at": _now_iso(),
            "prompt": prompt,
            "negative": negative,
            "sampler": sampler,
            "scheduler": scheduler,
        }
        sidecar = path.with_suffix(".json")
        sidecar.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")
        return item

    async def generate_cut(
        self,
        project_id: str,
        cut_id: int | str,
        *,
        seeds: Any = None,
        count: int = 1,
        model: str | None = None,
        steps: int | None = None,
        cfg: float | None = None,
        width: int | None = None,
        height: int | None = None,
        negative_extra: str = "",
        prompt_extra: str = "",
        sampler: str | None = None,
        scheduler: str | None = None,
    ) -> dict[str, Any]:
        project = self._load_project(project_id)
        compiled, _warnings, error = self._compile_plan(project)
        if error:
            raise ComicStudioError(f"콘티를 먼저 고쳐 주세요. {error}")
        cut = self._find_cut(compiled, cut_id)
        chosen_model = await self._resolve_checkpoint(model or compiled.get("model") or project.get("model"))
        recommended_steps, recommended_cfg = checkpoint_recommendation(chosen_model)
        chosen_steps = int(steps or cut.get("steps") or recommended_steps or 30)
        chosen_cfg = float(cfg or cut.get("cfg") or recommended_cfg or 5.5)
        chosen_width = self._safe_int(width or cut.get("width"), 832, 256, 2048)
        chosen_height = self._safe_int(height or cut.get("height"), 1216, 256, 2048)
        chosen_sampler = _text(sampler or cut.get("sampler")) or "euler"
        chosen_scheduler = _text(scheduler or cut.get("scheduler")) or "normal"
        positive = cut["prompt"]
        if prompt_extra.strip():
            positive = _dedupe_tags(positive, prompt_extra)
        negative = cut["negative"]
        if negative_extra.strip():
            negative = _dedupe_tags(negative, negative_extra)

        seed_list = self._seed_list(seeds, count)
        generated: list[dict[str, Any]] = []
        log_lines = [
            f"model: {chosen_model}",
            f"size: {chosen_width}x{chosen_height} | steps: {chosen_steps} | cfg: {chosen_cfg}",
            f"sampler: {chosen_sampler}/{chosen_scheduler}",
            f"prompt: {positive}",
        ]
        async with self._generation_lock:
            for seed in seed_list:
                workflow = self._build_workflow(
                    model=chosen_model,
                    prompt=positive,
                    negative=negative,
                    width=chosen_width,
                    height=chosen_height,
                    steps=chosen_steps,
                    cfg=chosen_cfg,
                    seed=seed,
                    sampler=chosen_sampler,
                    scheduler=chosen_scheduler,
                    prefix=f"pixelforge_comic/{project_id}_{cut['key']}_s{seed}",
                )
                data, elapsed = await self._render_one(
                    workflow=workflow,
                    timeout=int(self.settings.comic_studio.generation_timeout_seconds),
                )
                item = self._save_candidate(
                    project_id=project_id,
                    cut_key=cut["key"],
                    data=data,
                    seed=seed,
                    model=chosen_model,
                    steps=chosen_steps,
                    cfg=chosen_cfg,
                    width=chosen_width,
                    height=chosen_height,
                    prompt=positive,
                    negative=negative,
                    sampler=chosen_sampler,
                    scheduler=chosen_scheduler,
                    elapsed=elapsed,
                )
                generated.append(item)
                log_lines.append(f"saved {item['name']} seed={seed} ({elapsed:.1f}s)")
                state = project.setdefault("cuts", {}).setdefault(cut["key"], {})
                candidates = state.setdefault("candidates", [])
                candidates.append(item)
                self._save_project(project)
        state = (project.get("cuts") or {}).get(cut["key"]) or {}
        return {
            "project_id": project_id,
            "cut": self._cut_view(project_id, cut, state),
            "generated": generated,
            "model": chosen_model,
            "log": "\n".join(log_lines),
        }

    @staticmethod
    def _seed_list(raw: Any, count: int) -> list[int]:
        seeds: list[int] = []
        if isinstance(raw, str):
            parts = re.split(r"[,\s]+", raw.strip())
            for part in parts:
                if part:
                    try:
                        seeds.append(int(part))
                    except ValueError:
                        continue
        elif isinstance(raw, (list, tuple)):
            for part in raw:
                try:
                    seeds.append(int(part))
                except (TypeError, ValueError):
                    continue
        if seeds:
            return seeds[:6]
        wanted = max(1, min(6, int(count or 1)))
        return [random.randint(1, 2**31 - 1) for _ in range(wanted)]

    def pick_candidate(self, project_id: str, cut_id: int | str, candidate: str) -> dict[str, Any]:
        project = self._load_project(project_id)
        compiled, _warnings, error = self._compile_plan(project)
        if error:
            raise ComicStudioError(f"콘티를 먼저 고쳐 주세요. {error}")
        cut = self._find_cut(compiled, cut_id)
        name = _text(candidate)
        path = self._candidate_path(project_id, cut["key"], name)
        if not path.is_file():
            raise ComicStudioError("후보 이미지를 찾을 수 없습니다.")
        state = project.setdefault("cuts", {}).setdefault(cut["key"], {})
        names = self._state_candidate_names(state)
        if name not in names:
            state.setdefault("candidates", []).append({"name": name})
        state["selected"] = name
        self._save_project(project)
        return self._cut_view(project_id, cut, state)

    def clear_pick(self, project_id: str, cut_id: int | str) -> dict[str, Any]:
        project = self._load_project(project_id)
        compiled, _warnings, error = self._compile_plan(project)
        if error:
            raise ComicStudioError(f"콘티를 먼저 고쳐 주세요. {error}")
        cut = self._find_cut(compiled, cut_id)
        state = project.setdefault("cuts", {}).setdefault(cut["key"], {})
        state["selected"] = None
        self._save_project(project)
        return self._cut_view(project_id, cut, state)

    def delete_candidate(self, project_id: str, cut_id: int | str, candidate: str) -> dict[str, Any]:
        project = self._load_project(project_id)
        compiled, _warnings, error = self._compile_plan(project)
        if error:
            raise ComicStudioError(f"콘티를 먼저 고쳐 주세요. {error}")
        cut = self._find_cut(compiled, cut_id)
        name = _text(candidate)
        path = self._candidate_path(project_id, cut["key"], name)
        state = project.setdefault("cuts", {}).setdefault(cut["key"], {})
        state["candidates"] = [
            item
            for item in state.get("candidates") or []
            if (item.get("name") if isinstance(item, dict) else item) != name
        ]
        if state.get("selected") == name:
            state["selected"] = None
        if path.is_file():
            path.unlink()
        sidecar = path.with_suffix(".json")
        if sidecar.is_file():
            sidecar.unlink()
        self._save_project(project)
        return self._cut_view(project_id, cut, state)

    # ------------------------------------------------------------------- pages
    @staticmethod
    def _auto_layout(panel_count: int) -> str:
        if panel_count <= 1:
            return "1x1"
        if panel_count == 2:
            return "2x1"
        if panel_count == 3:
            return "3x1"
        if panel_count <= 4:
            return "2x2"
        return "2x3"

    def build_page(
        self,
        project_id: str,
        page_number: int,
        *,
        layout: str | None = None,
        width: int | None = None,
        height: int | None = None,
        title: str | None = None,
    ) -> dict[str, Any]:
        project = self._load_project(project_id)
        compiled, _warnings, error = self._compile_plan(project)
        if error:
            raise ComicStudioError(f"콘티를 먼저 고쳐 주세요. {error}")
        page = next(
            (item for item in compiled.get("pages") or [] if int(item.get("number") or 0) == int(page_number)),
            None,
        )
        if page is None:
            raise ComicStudioError(f"{page_number}페이지를 찾을 수 없습니다.")
        panels: list[dict[str, Any]] = []
        missing: list[int] = []
        cut_lookup = {cut["id"]: cut for cut in compiled.get("cuts") or []}
        states = project.get("cuts") if isinstance(project.get("cuts"), dict) else {}
        for cut_id in page.get("cut_ids") or []:
            cut = cut_lookup.get(cut_id)
            if not cut:
                continue
            state = states.get(cut["key"]) if isinstance(states, dict) else {}
            selected = _text((state or {}).get("selected"))
            if not selected:
                missing.append(int(cut_id))
                continue
            try:
                path = self._candidate_path(project_id, cut["key"], selected)
            except ComicStudioError:
                missing.append(int(cut_id))
                continue
            if not path.is_file():
                missing.append(int(cut_id))
                continue
            panels.append(
                {
                    "path": str(path),
                    "text": str(cut.get("text") or ""),
                    "position": str(cut.get("position") or "top"),
                }
            )
        if missing:
            raise ComicStudioError(
                "최종 이미지를 먼저 골라야 합니다. 컷 " + ", ".join(str(item) for item in missing)
            )
        if not panels:
            raise ComicStudioError("페이지에 넣을 컷이 없습니다.")
        chosen_layout = _text(layout) or self._auto_layout(len(panels))
        page_width = self._safe_int(width, self.settings.comic_studio.page_width, 600, 2400)
        page_height = self._safe_int(height, self.settings.comic_studio.page_height, 600, 3400)
        page_title = _text(title) or str(project.get("title") or "")
        result = self.comic.build_page(
            panels,
            layout=chosen_layout,
            width=page_width,
            height=page_height,
            title=page_title,
        )
        old_pages = [item for item in project.get("pages") or [] if int(item.get("number") or 0) == int(page_number)]
        for old in old_pages:
            old_id = str(old.get("id") or "")
            if old_id and old_id != result["id"]:
                self.comic.delete_page(old_id)
        record = {
            **result,
            "number": int(page_number),
            "note": page.get("note") or "",
            "path": str(self.comic.pages_dir / f"page_{result['id']}.png"),
            "created_at": _now_iso(),
        }
        project["pages"] = [
            item for item in project.get("pages") or [] if int(item.get("number") or 0) != int(page_number)
        ]
        project["pages"].append(record)
        project["pages"].sort(key=lambda item: int(item.get("number") or 0))
        self._save_project(project)
        return record

    def delete_page(self, project_id: str, page_number: int) -> dict[str, Any]:
        project = self._load_project(project_id)
        removed = []
        keep = []
        for item in project.get("pages") or []:
            if int(item.get("number") or 0) == int(page_number):
                page_id = str(item.get("id") or "")
                if page_id:
                    self.comic.delete_page(page_id)
                removed.append(item)
            else:
                keep.append(item)
        project["pages"] = keep
        self._save_project(project)
        if not removed:
            raise ComicStudioError(f"{page_number}페이지를 찾을 수 없습니다.")
        return {"id": project_id, "page": page_number, "deleted": True}

    def export_pdf(self, project_id: str) -> Path:
        project = self._load_project(project_id)
        pages = sorted(
            [item for item in project.get("pages") or [] if item.get("path")],
            key=lambda item: int(item.get("number") or 0),
        )
        if not pages:
            raise ComicStudioError("먼저 페이지를 하나 이상 조립해 주세요.")
        images: list[Image.Image] = []
        try:
            for page in pages:
                path = Path(str(page.get("path")))
                if not path.is_file():
                    raise ComicStudioError(f"{page.get('number')}페이지 파일을 찾을 수 없습니다.")
                with Image.open(path) as raw:
                    raw.load()
                    images.append(raw.convert("RGB"))
            if not images:
                raise ComicStudioError("내보낼 페이지가 없습니다.")
            export_dir = self._project_dir(project_id) / "exports"
            export_dir.mkdir(parents=True, exist_ok=True)
            pdf_path = export_dir / "comic.pdf"
            first, rest = images[0], images[1:]
            first.save(
                pdf_path,
                format="PDF",
                resolution=150.0,
                save_all=True,
                append_images=rest,
            )
            return pdf_path
        finally:
            for image in images:
                image.close()

    def resolve_asset(self, project_id: str, relative_path: str) -> tuple[Path, str]:
        root = self._project_dir(project_id).resolve()
        candidate = (root / relative_path.lstrip("/\\")).resolve()
        if root != candidate and root not in candidate.parents:
            raise ComicStudioError("허용되지 않은 경로입니다.")
        if not candidate.is_file():
            raise ComicStudioError("파일을 찾을 수 없습니다.")
        suffix = candidate.suffix.lower()
        media = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".pdf": "application/pdf",
        }.get(suffix)
        if not media:
            raise ComicStudioError("이미지나 PDF만 열 수 있습니다.")
        return candidate, media
