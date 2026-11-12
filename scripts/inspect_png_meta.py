"""Print the ComfyUI prompt metadata stored in a PNG (model, steps, flow)."""

import json
import sys
from pathlib import Path

from PIL import Image

sys.stdout.reconfigure(encoding="utf-8")

for raw in sys.argv[1:]:
    path = Path(raw)
    if not path.is_file():
        print(f"[missing] {path}")
        continue
    image = Image.open(path)
    text = getattr(image, "text", {}) or {}
    prompt = text.get("prompt")
    data = json.loads(prompt) if prompt else {}
    models = sorted(
        {
            str((node.get("inputs") or {}).get("ckpt_name"))
            for node in data.values()
            if isinstance(node, dict)
            and node.get("class_type") == "CheckpointLoaderSimple"
        }
    )
    unets = sorted(
        {
            str((node.get("inputs") or {}).get("unet_name"))
            for node in data.values()
            if isinstance(node, dict) and node.get("class_type") == "UNETLoader"
        }
    )
    samplers = [
        {
            "steps": (node.get("inputs") or {}).get("steps"),
            "cfg": (node.get("inputs") or {}).get("cfg"),
            "sampler": (node.get("inputs") or {}).get("sampler_name"),
            "scheduler": (node.get("inputs") or {}).get("scheduler"),
        }
        for node in data.values()
        if isinstance(node, dict)
        and node.get("class_type") in ("KSampler", "KSamplerAdvanced")
    ]
    print(f"{path.name}: checkpoints={models or '-'} unets={unets or '-'} samplers={samplers or '-'}")
