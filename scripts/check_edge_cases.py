# -*- coding: utf-8 -*-
"""Edge-case checks: tile mode, duplicate-object prompt, original palette."""
from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8765/api"


def post(path: str, payload: dict) -> dict:
    request = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read())


def get(path: str) -> dict:
    with urllib.request.urlopen(BASE + path) as response:
        return json.loads(response.read())


CASES = [
    {
        "name": "tile_forest",
        "prompt": "픽셀아트 숲 배경 타일 만들어줘",
        "mode": "tile",
        "size": 64,
        "seed": 1234567,
        "transparent": False,
        "palette": 16,
        "resize_filter": "nearest",
    },
    {
        "name": "duplicate_apples",
        "prompt": "빨간색 사과 네 개 만들어줘",
        "mode": "icon",
        "size": 64,
        "seed": 7654321,
        "transparent": True,
        "palette": 16,
        "resize_filter": "nearest",
    },
    {
        "name": "duplicate_apples_positive_seed",
        "prompt": "빨간색 사과 네 개 만들어줘",
        "mode": "icon",
        "size": 64,
        "seed": 1234567,
        "transparent": True,
        "palette": 16,
        "resize_filter": "nearest",
    },
    {
        "name": "original_palette_tree",
        "prompt": "나무 한 그루 만들어줘",
        "mode": "object",
        "size": 64,
        "seed": 1234567,
        "transparent": True,
        "palette": 0,
        "resize_filter": "nearest",
    },
]

records = []
for case in CASES:
    payload = {
        "prompt": case["prompt"],
        "mode": case["mode"],
        "output_size": case["size"],
        "seed": case["seed"],
        "steps": 28,
        "cfg": 6.0,
        "lora_strength": 0.8,
        "transparent": case["transparent"],
        "postprocess": "quantize",
        "palette_colors": case["palette"],
        "resize_filter": case["resize_filter"],
        "candidates": 4,
    }
    response = post("/generate", payload)
    job_id = response["job_id"]
    print(f"[{case['name']}] submitted {job_id}", flush=True)
    while True:
        time.sleep(1.5)
        job = get(f"/jobs/{job_id}")
        if job["status"] in {"completed", "error", "cancelled"}:
            break
    if job["status"] != "completed":
        print("  FAILED:", job.get("error"))
        records.append({**case, "job_id": job_id, "status": job["status"], "error": job.get("error")})
        continue
    result = job["result"]
    path = ROOT / "outputs" / "pixel_art" / f"{job_id}_pixel_{case['size']}.png"
    image = Image.open(path)
    arr = np.asarray(image)
    mask = arr[:, :, 3] > 0 if arr.ndim == 3 and arr.shape[2] == 4 else np.ones(arr.shape[:2], bool)
    _, count = ndimage.label(mask, structure=np.ones((3, 3), dtype=bool))
    passed = sum(c["passed"] for c in result["quality"])
    panel_failed = any(
        c["key"] == "no_card_panel" and not c["passed"] for c in result["quality"]
    )
    print(
        f"  subject={job['prompt_plan']['subject']!r} mode={result['mode']} "
        f"transparent={result['transparent']} palette={result['palette_colors']} "
        f"resize={result['resize_filter']} components={count} "
        f"fill={result['subject_fill']:.3f} quality={passed}/{len(result['quality'])} "
        f"candidate=#{result['candidate_index'] + 1}/{result['candidates_generated']} "
        f"score={result['candidate_score']:.1f} panel={result['panel_suspected']}"
    )
    records.append(
        {
            **case,
            "job_id": job_id,
            "status": job["status"],
            "selected_seed": job["seed_used"],
            "base_seed": job.get("base_seed"),
            "candidates_generated": result["candidates_generated"],
            "candidate_index": result["candidate_index"],
            "candidate_score": result["candidate_score"],
            "panel_suspected": result["panel_suspected"],
            "panel_failed": panel_failed,
            "components": count,
            "quality_passed": passed,
            "quality_total": len(result["quality"]),
            "warnings": result["warnings"],
        }
    )
    for warning in result["warnings"]:
        print("  warning:", warning)

report = ROOT / "experiments" / "edge_cases_candidates.json"
report.parent.mkdir(exist_ok=True)
report.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
print("report:", report)
