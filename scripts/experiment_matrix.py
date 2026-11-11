"""Focused SDXL/LoRA experiments for PixelForge composition quality.

Runs direct ComfyUI API calls and saves every raw generation under
``experiments/`` so the images can be compared side by side.
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMFY = "http://127.0.0.1:8188"
OUT_DIR = ROOT / "experiments"

POSITIVE = {
    "current": (
        "pixel, pixel art, library building, single isolated object, centered composition, "
        "front view, game icon, clear silhouette, limited color palette, readable at small "
        "resolution, no unnecessary details, large in frame, front facade, rectangular, door "
        "and windows, 32x32 style, clean pixel art, isolated on a plain solid white background, "
        "no shadow, no ground plane, no border, no frame, no background scenery, no other objects"
    ),
    "sentence": (
        "pixel art of one single library building, a standalone library, one complete building "
        "visible, centered, front view, entire building in frame, game asset, clear bold "
        "silhouette, simple readable shape, clean edges, limited color palette, plain pure white "
        "background, no scenery, no ground"
    ),
    "tag": (
        "pixel art, 16-bit, one library building, single object, front view, centered, full "
        "building, game asset icon, bold silhouette, limited palette, clean silhouette, white "
        "background, no background"
    ),
}

NEGATIVE = {
    "current": (
        "sprite sheet, multiple objects, multiple characters, collage, contact sheet, multiple "
        "views, split panels, grid layout, text, labels, watermark, frame, border, blurry, "
        "photorealistic, 3d render, excessive gradients, anti-aliased edges, extra objects, "
        "background scenery, ground shadow, scene, soft, smooth, gradient, photograph"
    ),
    "strict": (
        "sprite sheet, multiple buildings, two buildings, duplicate, repeated object, grid, "
        "collage, contact sheet, multiple views, split panels, panels, sequence, set, collection, "
        "text, letters, numbers, labels, watermark, signature, frame, border, background, "
        "scenery, landscape, sky, ground, floor, shadow, people, trees, cars, blurry, "
        "photorealistic, 3d render, gradient, anti-aliasing, soft edges, noise"
    ),
}


def post_json(path: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        COMFY + path, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read())


def get_json(path: str) -> dict:
    with urllib.request.urlopen(COMFY + path, timeout=30) as response:
        return json.loads(response.read())


def get_bytes(path: str) -> bytes:
    with urllib.request.urlopen(COMFY + path, timeout=60) as response:
        return response.read()


def load_workflow() -> dict:
    with (ROOT / "workflows" / "text_to_pixel.json").open(encoding="utf-8") as handle:
        return json.load(handle)


def run(name: str, positive: str, negative: str, size: int, seed: int,
        steps: int, cfg: float, lora: float) -> Path:
    workflow = load_workflow()
    workflow["1"]["inputs"]["ckpt_name"] = "sd_xl_base_1.0.safetensors"
    workflow["2"]["inputs"]["lora_name"] = "pixel-art-xl.safetensors"
    workflow["2"]["inputs"]["strength_model"] = lora
    workflow["2"]["inputs"]["strength_clip"] = lora
    workflow["3"]["inputs"]["text"] = positive
    workflow["4"]["inputs"]["text"] = negative
    workflow["5"]["inputs"]["width"] = size
    workflow["5"]["inputs"]["height"] = size
    workflow["6"]["inputs"].update(
        {"seed": seed, "steps": steps, "cfg": cfg,
         "sampler_name": "dpmpp_2m", "scheduler": "karras"}
    )
    workflow["8"]["inputs"]["filename_prefix"] = f"pixelforge-exp/{name}"

    client_id = uuid.uuid4().hex
    started = time.monotonic()
    response = post_json("/prompt", {"prompt": workflow, "client_id": client_id})
    prompt_id = response["prompt_id"]
    while True:
        history = get_json(f"/history/{prompt_id}")
        entry = history.get(prompt_id)
        if entry:
            status = entry.get("status") or {}
            if status.get("status_str") == "error":
                raise RuntimeError(json.dumps(status, ensure_ascii=False)[:2000])
            if status.get("completed") is not False and entry.get("outputs"):
                break
        if time.monotonic() - started > 240:
            raise TimeoutError(name)
        time.sleep(1.0)

    outputs = entry["outputs"]
    image = None
    for node in outputs.values():
        if node.get("images"):
            image = node["images"][0]
            break
    if image is None:
        raise RuntimeError(f"No image for {name}")
    data = get_bytes(
        "/view?filename={}&subfolder={}&type={}".format(
            urllib.parse.quote(image["filename"]),
            urllib.parse.quote(image.get("subfolder") or ""),
            urllib.parse.quote(image.get("type") or "output"),
        )
    )
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{name}.png"
    path.write_bytes(data)
    elapsed = time.monotonic() - started
    print(f"{name:44s} {size:4d}px  {elapsed:6.2f}s  -> {path.name}")
    return path


def seed_list(value: str) -> list[int]:
    return [int(part) for part in value.split(",") if part.strip()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", default="resolution")
    parser.add_argument("--seeds", default="1234567")
    args = parser.parse_args()
    seeds = seed_list(args.seeds)

    if args.plan == "resolution":
        for size in (512, 768, 1024):
            for prompt_name in ("current", "sentence"):
                for seed in seeds:
                    run(
                        f"res{size}_{prompt_name}_s{seed}",
                        POSITIVE[prompt_name], NEGATIVE["strict"],
                        size, seed, 28, 6.0, 0.8,
                    )
    elif args.plan == "prompt":
        for prompt_name in ("current", "sentence", "tag"):
            for seed in seeds:
                run(
                    f"p1024_{prompt_name}_s{seed}",
                    POSITIVE[prompt_name], NEGATIVE["strict"],
                    1024, seed, 28, 6.0, 0.8,
                )
    elif args.plan == "subjects":
        subjects = {
            "cat": (
                "pixel art of one single cute cat character, a small cat, full body from head "
                "to toe, standing, centered, entire character in frame, game sprite, clear bold "
                "silhouette, simple readable shape, clean edges, limited color palette, plain "
                "pure white background, no scenery, no ground, no shadow"
            ),
            "tree": (
                "pixel art of one single tree, one complete tree visible, centered, game asset "
                "icon, clear bold silhouette, simple readable shape, clean edges, limited color "
                "palette, plain pure white background, no scenery, no ground, no shadow"
            ),
            "apple": (
                "pixel art of one single red apple, one whole apple, centered, game asset icon, "
                "clear bold silhouette, simple readable shape, clean edges, limited color "
                "palette, plain pure white background, no scenery, no ground, no shadow"
            ),
            "school": (
                "pixel art of one single school building, a standalone school, one complete "
                "building visible, centered, front view, entire building in frame, game asset, "
                "clear bold silhouette, simple readable shape, clean edges, limited color "
                "palette, plain pure white background, no scenery, no ground"
            ),
        }
        for subject, text in subjects.items():
            for seed in seeds:
                run(
                    f"subject_{subject}_s{seed}", text, NEGATIVE["strict"],
                    512, seed, 28, 6.0, 0.8,
                )
    elif args.plan == "bg":
        base = (
            "pixel art of one single library building, a standalone library, one complete "
            "building visible, centered, front view, entire building in frame, game asset, "
            "clear bold silhouette, simple readable shape, clean edges, limited color palette, "
            "{bg}, no scenery, no ground"
        )
        backgrounds = {
            "white": "plain pure white background",
            "magenta": "solid flat bright magenta background",
            "green": "solid flat chroma key green background",
            "blue": "solid flat bright cyan blue background",
        }
        for bg_name, bg_text in backgrounds.items():
            for seed in seeds:
                run(
                    f"bg{bg_name}_s{seed}", base.format(bg=bg_text), NEGATIVE["strict"],
                    512, seed, 28, 6.0, 0.8,
                )
    elif args.plan == "sampling512":
        subjects = {
            "lib": POSITIVE["sentence"],
            "cat": (
                "pixel art of one single cute cat character, a small cat, full body from head "
                "to toe, standing, centered, entire character in frame, game sprite, clear bold "
                "silhouette, simple readable shape, clean edges, limited color palette, plain "
                "pure white background, no scenery, no ground, no shadow"
            ),
        }
        combos = [
            ("lora060", 28, 6.0, 0.6),
            ("lora080", 28, 6.0, 0.8),
            ("lora100", 28, 6.0, 1.0),
            ("cfg50", 28, 5.0, 0.8),
            ("cfg60", 28, 6.0, 0.8),
            ("cfg70", 28, 7.0, 0.8),
            ("steps24", 24, 6.0, 0.8),
            ("steps32", 32, 6.0, 0.8),
        ]
        for subject, text in subjects.items():
            for label, steps, cfg, lora in combos:
                for seed in seeds:
                    run(
                        f"s512_{subject}_{label}_s{seed}", text, NEGATIVE["strict"],
                        512, seed, steps, cfg, lora,
                    )
    elif args.plan == "sampling":
        for lora in (0.6, 0.8, 1.0):
            for seed in seeds:
                run(
                    f"lora{lora}_s{seed}", POSITIVE["sentence"], NEGATIVE["strict"],
                    1024, seed, 28, 6.0, lora,
                )
        for cfg in (5.0, 6.0, 7.0):
            for seed in seeds:
                run(
                    f"cfg{cfg}_s{seed}", POSITIVE["sentence"], NEGATIVE["strict"],
                    1024, seed, 28, cfg, 0.8,
                )
        for steps in (24, 32):
            for seed in seeds:
                run(
                    f"steps{steps}_s{seed}", POSITIVE["sentence"], NEGATIVE["strict"],
                    1024, seed, steps, 6.0, 0.8,
                )
    else:
        raise SystemExit(f"unknown plan {args.plan}")


if __name__ == "__main__":
    import urllib.parse

    main()
