"""Generate the built-in reference sample images with the local ComfyUI.

The samples give users a quick way to try the image-to-image page without
uploading their own photos. They are rendered once with the local SDXL
checkpoint and stored under ``assets/references/samples`` together with the
``samples.json`` index the backend reads.

Usage::

    backend\\.venv\\Scripts\\python.exe scripts\\make_reference_samples.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.config import get_settings  # noqa: E402

COMFY_URL = "http://127.0.0.1:8188"
SAMPLES_DIR = PROJECT_ROOT / "assets" / "references" / "samples"

SAMPLES = [
    {
        "id": "sample_portrait",
        "file": "sample_portrait.png",
        "name": "인물 초상",
        "hint": "얼굴·외형 참고용 인물 사진",
        "prompt": (
            "studio portrait photo of a young woman with short dark hair, "
            "soft window light, plain grey background, calm expression, "
            "looking at camera, high detail, 85mm lens"
        ),
        "width": 768,
        "height": 1024,
    },
    {
        "id": "sample_animal",
        "file": "sample_animal.png",
        "name": "동물 야생",
        "hint": "동물 외형·질감 참고용 사진",
        "prompt": (
            "wildlife photograph of a red fox sitting in an autumn forest, "
            "warm rim light, shallow depth of field, detailed fur, "
            "professional nature photography"
        ),
        "width": 1024,
        "height": 768,
    },
    {
        "id": "sample_style",
        "file": "sample_style.png",
        "name": "화풍 · 수채화",
        "hint": "화풍·그림체 참고용 일러스트",
        "prompt": (
            "watercolor illustration of a lighthouse during a storm, "
            "loose brush strokes, pigment texture, muted blue palette, "
            "painterly paper grain"
        ),
        "width": 1024,
        "height": 768,
    },
    {
        "id": "sample_scene",
        "file": "sample_scene.png",
        "name": "장면 · 구도",
        "hint": "구도·공간 배치 참고용 장면",
        "prompt": (
            "neon cyberpunk alley in the rain, wet asphalt reflections, "
            "wide angle establishing shot, cinematic lighting, "
            "depth of field, moody atmosphere"
        ),
        "width": 1024,
        "height": 768,
    },
]

NEGATIVE = (
    "blurry, low quality, jpeg artifacts, watermark, text, signature, "
    "deformed, bad anatomy, extra limbs, cropped, out of frame"
)


def build_workflow(prompt: str, width: int, height: int, seed: int) -> dict:
    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"},
        },
        "2": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": prompt, "clip": ["1", 1]},
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": NEGATIVE, "clip": ["1", 1]},
        },
        "4": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": width, "height": height, "batch_size": 1},
        },
        "5": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed,
                "steps": 26,
                "cfg": 5.5,
                "sampler_name": "dpmpp_2m",
                "scheduler": "karras",
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
            "inputs": {
                "filename_prefix": "pixelforge/samples",
                "images": ["6", 0],
            },
        },
    }


def wait_for(client: httpx.Client, prompt_id: str, timeout: float = 600) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"{COMFY_URL}/history/{prompt_id}", timeout=20)
        if response.status_code == 200:
            entry = response.json().get(prompt_id)
            if entry:
                status = entry.get("status") or {}
                if status.get("status_str") == "error":
                    raise RuntimeError(f"ComfyUI error: {json.dumps(status)[:500]}")
                outputs = entry.get("outputs") or {}
                for node_output in outputs.values():
                    for image in (node_output or {}).get("images") or []:
                        if image.get("filename"):
                            return image
        time.sleep(1.5)
    raise TimeoutError(f"Timed out waiting for prompt {prompt_id}")


def main() -> int:
    settings = get_settings()
    checkpoint = settings.generation.reference_checkpoint or "sd_xl_base_1.0.safetensors"
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    index: list[dict] = []
    with httpx.Client(follow_redirects=True) as client:
        try:
            client.get(f"{COMFY_URL}/system_stats", timeout=10)
        except Exception as exc:  # pragma: no cover - manual script
            print(f"ComfyUI is not reachable at {COMFY_URL}: {exc}")
            return 1
        for offset, sample in enumerate(SAMPLES):
            target = SAMPLES_DIR / sample["file"]
            if target.exists():
                print(f"skip (exists): {target.name}")
            else:
                workflow = build_workflow(
                    sample["prompt"],
                    sample["width"],
                    sample["height"],
                    seed=20240517 + offset * 101,
                )
                workflow["1"]["inputs"]["ckpt_name"] = checkpoint
                response = client.post(
                    f"{COMFY_URL}/prompt",
                    json={"prompt": workflow, "client_id": "pixelforge-samples"},
                    timeout=30,
                )
                response.raise_for_status()
                prompt_id = response.json()["prompt_id"]
                print(f"queued {sample['id']} ({prompt_id})")
                image = wait_for(client, prompt_id)
                content = client.get(
                    f"{COMFY_URL}/view",
                    params={
                        "filename": image["filename"],
                        "subfolder": image.get("subfolder", ""),
                        "type": image.get("type", "output"),
                    },
                    timeout=60,
                )
                target.write_bytes(content.content)
                print(f"saved {target.name}")
            index.append(
                {
                    "id": sample["id"],
                    "file": sample["file"],
                    "name": sample["name"],
                    "hint": sample["hint"],
                }
            )
    index_path = SAMPLES_DIR / "samples.json"
    index_path.write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"wrote {index_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
