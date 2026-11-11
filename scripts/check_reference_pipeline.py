"""Regression check for the image-to-image (reference) pipeline.

Exercises the backend end to end: sample catalogue, upload + analysis,
IP-Adapter capability reporting, single/multi reference generation, the
reference gallery and result deletion.

Usage::

    backend\\.venv\\Scripts\\python.exe scripts\\check_reference_pipeline.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.config import get_settings  # noqa: E402

API = "http://127.0.0.1:8765"
SAMPLES_DIR = PROJECT_ROOT / "assets" / "references" / "samples"

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"


def check(label: str, condition: bool, detail: str = "") -> bool:
    mark = PASS if condition else FAIL
    print(f"[{mark}] {label}{(' · ' + detail) if detail else ''}")
    return condition


def wait_for_job(client: httpx.Client, job_id: str, timeout: float = 600) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"{API}/api/jobs/{job_id}").json()
        if job["status"] in {"completed", "error", "cancelled"}:
            return job
        time.sleep(2)
    raise TimeoutError(f"job {job_id} did not finish in time")


def build_payload(**overrides) -> dict:
    payload = {
        "prompt": "a young woman in a red coat on a snowy street, cinematic lighting",
        "negative_prompt": "blurry, low quality, watermark, text",
        "kind": "reference",
        "mode": "icon",
        "output_size": 64,
        "seed": 4242,
        "steps": 22,
        "cfg": 6.0,
        "lora_strength": 0.0,
        "transparent": False,
        "postprocess": "quantize",
        "palette_colors": 0,
        "resize_filter": "nearest",
        "candidates": 1,
        "checkpoint": "sd_xl_base_1.0.safetensors",
        "lora": "",
        "image_size": 768,
        "translate_prompt": False,
    }
    payload.update(overrides)
    return payload


def main() -> int:
    settings = get_settings()
    ok = True
    with httpx.Client(timeout=600) as client:
        samples = client.get(f"{API}/api/references/samples").json()["items"]
        ok &= check("샘플 목록 제공", len(samples) >= 4, f"{len(samples)}개")
        ok &= check(
            "샘플 분석 정보 포함",
            all(item["analysis"]["summary"] for item in samples),
        )

        capabilities = client.get(
            f"{API}/api/references/capabilities",
            params={"checkpoint": "sd_xl_base_1.0.safetensors"},
        ).json()
        ok &= check(
            "IP-Adapter 사용 가능",
            capabilities["available"],
            f"node={capabilities['node_installed']} plus={capabilities['plus_model']} "
            f"clip={capabilities['clip_vision_model']}",
        )
        ok &= check(
            "SDXL 체크포인트 호환",
            capabilities["checkpoint_compatible"] is True,
            capabilities["checkpoint_note"][:60],
        )

        source = SAMPLES_DIR / "sample_portrait.png"
        upload = client.post(
            f"{API}/api/references/upload",
            files={"file": ("check_reference.png", source.read_bytes(), "image/png")},
        ).json()
        ok &= check("참고 이미지 업로드", upload["id"].startswith("up_"), upload["id"])
        ok &= check(
            "업로드 이미지 분석",
            bool(upload["analysis"]["summary"]),
            upload["analysis"]["summary"],
        )

        single = client.post(
            f"{API}/api/generate",
            json=build_payload(
                reference_images=[
                    {"asset_id": upload["id"], "strength": 0.85, "focus": "face"}
                ]
            ),
        ).json()
        job = wait_for_job(client, single["job_id"])
        ok &= check("1장 레퍼런스 생성", job["status"] == "completed", job.get("error") or "")
        if job["status"] == "completed":
            references = (job.get("result") or {}).get("references") or []
            ok &= check(
                "결과에 참고 이미지 기록",
                len(references) == 1 and references[0]["focus"] == "face",
                str(references[:1]),
            )
            image_url = (job.get("result") or {}).get("image_url")
            ok &= check("결과 이미지 URL", bool(image_url), str(image_url))

        multi = client.post(
            f"{API}/api/generate",
            json=build_payload(
                seed=777,
                reference_images=[
                    {"asset_id": "sample_portrait", "strength": 0.8, "focus": "face"},
                    {"asset_id": "sample_style", "strength": 0.55, "focus": "style"},
                ],
            ),
        ).json()
        job2 = wait_for_job(client, multi["job_id"])
        ok &= check("2장 레퍼런스 생성", job2["status"] == "completed", job2.get("error") or "")
        if job2["status"] == "completed":
            references = (job2.get("result") or {}).get("references") or []
            ok &= check("2장 모두 기록", len(references) == 2, str(len(references)))

        zero = client.post(
            f"{API}/api/generate",
            json=build_payload(
                seed=99,
                prompt="a red fox in an autumn forest",
                reference_images=[
                    {"asset_id": "sample_animal", "strength": 0.0, "focus": "appearance"}
                ],
            ),
        ).json()
        job3 = wait_for_job(client, zero["job_id"])
        ok &= check("강도 0 생성", job3["status"] == "completed", job3.get("error") or "")

        outputs = client.get(f"{API}/api/outputs", params={"kind": "reference"}).json()
        ok &= check("레퍼런스 갤러리", len(outputs["items"]) >= 3, f"{len(outputs['items'])}개")

        image_outputs = client.get(f"{API}/api/outputs", params={"kind": "image"}).json()
        pixel_outputs = client.get(f"{API}/api/outputs", params={"kind": "pixel"}).json()
        ok &= check(
            "기존 이미지/픽셀 갤러리 유지",
            len(image_outputs["items"]) >= 1 and len(pixel_outputs["items"]) >= 1,
            f"image={len(image_outputs['items'])} pixel={len(pixel_outputs['items'])}",
        )

        if job["status"] == "completed":
            deleted = client.delete(f"{API}/api/outputs/{single['job_id']}").json()
            ok &= check("결과 삭제", deleted["count"] > 0, f"{deleted['count']}개")

    print("\nRESULT:", "ALL PASS" if ok else "FAILURES FOUND")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
