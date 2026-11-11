# -*- coding: utf-8 -*-
"""Print the structured prompt plan for the five required Korean requests."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import get_settings  # noqa: E402
from app.services.prompt_engine import build_prompt_plan  # noqa: E402

PROMPTS = [
    ("도서관 아이콘 만들어줘", "icon"),
    ("귀여운 고양이 캐릭터 한 명 만들어줘", "character"),
    ("나무 한 그루 만들어줘", "object"),
    ("빨간색 사과 하나 만들어줘", "object"),
    ("작은 픽셀아트 학교 건물 만들어줘", "icon"),
]

settings = get_settings()
for text, mode in PROMPTS:
    plan = build_prompt_plan(text, None, mode, True, 64, settings.generation)
    print(f"[{mode}] {text}")
    print(f"  subject: {plan.subject}")
    print(f"  view: {plan.view} / {plan.composition}")
    print(f"  positive: {plan.positive}")
    print()
