"""Write nk comic-studio drawing workflows (one per installed SDXL model).

nk can draw a solo cut with a user workflow (``workflows/<name>.json``) and the
studio already exposes those in its "그림 워크플로" dropdown. This script turns
every installed SDXL checkpoint into such a workflow, so the studio dropdown
becomes a model picker without touching a single line of nk code.

Usage::

    backend\\.venv\\Scripts\\python.exe scripts\\make_nk_model_flows.py
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import httpx

sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMFY_URL = os.environ.get("PIXELFORGE_COMFY_URL", "http://127.0.0.1:8188")
NK_HOME = os.environ.get("NK_HOME") or r"C:\nk"
FLOW_DIR = Path(NK_HOME) / "workflows"

# nk flow slot titles (see nk_flow.py: find_slots / _titled_default).
TITLES = {
    "6": "NK prompt",
    "7": "NK negative",
    "3": "NK seed",
    "5": "NK size",
    "9": "NK output",
    "20": "NK lora",
}

# Same prompt template nk exports for its own default flow.
PROMPT_TEMPLATE = "%quality%, %artist%, safe, %char%, %scene%"

FLOW_RE = re.compile(r"^[A-Za-z0-9_\-\uac00-\ud7a3.]{1,60}$")


def slug(model: str) -> str:
    base = Path(model).stem
    base = re.sub(r"[^A-Za-z0-9_\-\uac00-\ud7a3.]", "_", base)
    return base[:60]


def checkpoints() -> list[tuple[str, int, float]]:
    """(name, steps, cfg) for every SDXL checkpoint ComfyUI knows about."""
    with httpx.Client(timeout=60) as client:
        info = client.get(f"{COMFY_URL}/object_info/CheckpointLoaderSimple").json()
    names = info["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0]
    out: list[tuple[str, int, float]] = []
    for name in names:
        lowered = name.lower()
        if any(
            token in lowered
            for token in ("hunyuan", "sam3", "svd", "flux", "sd3", "anima", "ace_step", "acestep")
        ):
            continue
        out.append((name, 30, 5.5))
    return out


def recommended_values() -> dict[str, tuple[int, float]]:
    """Per model steps/cfg from PixelForge's own catalog (best effort)."""
    values: dict[str, tuple[int, float]] = {}
    try:
        with httpx.Client(timeout=60) as client:
            health = client.get("http://127.0.0.1:8765/api/health").json()
        for model in health.get("models", {}).get("checkpoints", []):
            if model.get("recommended_steps") and model.get("recommended_cfg"):
                values[model["name"]] = (
                    int(model["recommended_steps"]),
                    float(model["recommended_cfg"]),
                )
    except Exception:
        pass
    return values


def first_lora() -> str:
    models = Path(
        os.environ.get(
            "LOCALAPPDATA", str(Path.home() / "AppData" / "Local")
        )
    ) / "Comfy-Desktop" / "ComfyUI-Shared" / "models" / "loras"
    if models.is_dir():
        for path in sorted(models.glob("*.safetensors")):
            return path.name
    return ""


def build_graph(model: str, steps: int, cfg: float, lora: str, prefix: str) -> dict:
    clip = ["20", 1] if lora else ["4", 1]
    model_link = ["20", 0] if lora else ["4", 0]
    graph = {
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": model},
            "_meta": {"title": "CheckpointLoaderSimple"},
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": PROMPT_TEMPLATE, "clip": clip},
            "_meta": {"title": TITLES["6"]},
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "%negative%", "clip": clip},
            "_meta": {"title": TITLES["7"]},
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": 832, "height": 1216, "batch_size": 1},
            "_meta": {"title": TITLES["5"]},
        },
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": 1,
                "steps": int(steps),
                "cfg": float(cfg),
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
                "model": model_link,
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0],
            },
            "_meta": {"title": TITLES["3"]},
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
            "_meta": {"title": "VAEDecode"},
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": prefix, "images": ["8", 0]},
            "_meta": {"title": TITLES["9"]},
        },
    }
    if lora:
        graph["20"] = {
            "class_type": "LoraLoader",
            "inputs": {
                "model": ["4", 0],
                "clip": ["4", 1],
                "lora_name": lora,
                "strength_model": 0.0,
                "strength_clip": 0.0,
            },
            "_meta": {"title": TITLES["20"]},
        }
    return graph


def main() -> int:
    kit = Path(NK_HOME)
    if not (kit / "nk.py").is_file():
        print(f"[ERROR] nk kit not found at {kit}")
        return 1
    FLOW_DIR.mkdir(parents=True, exist_ok=True)
    values = recommended_values()
    lora = first_lora()
    written = 0
    for model, default_steps, default_cfg in checkpoints():
        steps, cfg = values.get(model, (default_steps, default_cfg))
        name = slug(model)
        if not FLOW_RE.match(name):
            print(f"[skip] flow name not allowed: {name}")
            continue
        graph = build_graph(model, steps, cfg, lora, f"nk/{name}")
        path = FLOW_DIR / f"{name}.json"
        path.write_text(
            json.dumps(graph, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        written += 1
        print(f"[flow] {name:38} {model}  steps={steps} cfg={cfg}")

    # Let nk validate what we wrote (it knows the flow rules better than us).
    for name in [p.stem for p in FLOW_DIR.glob("*.json")]:
        result = subprocess.run(
            [sys.executable, "nk.py", "ep", "flow", "check", name],
            cwd=str(kit),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        tail = (result.stdout or "").strip().splitlines()[-2:]
        status = "OK" if result.returncode == 0 else "PROBLEM"
        print(f"[check] {name:38} {status} · {' / '.join(tail)}")

    print(f"\n{written} workflows written to {FLOW_DIR}")
    print("nk 작업실의 '그림 워크플로' 드롭다운에서 모델을 고를 수 있습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
