"""Render one comic cut with Pony to check the automatic score tags."""

import sys
import time

import httpx

sys.stdout.reconfigure(encoding="utf-8")

client = httpx.Client(base_url="http://127.0.0.1:8765", timeout=900)

payload = {
    "prompt": "a girl with short hair wearing a red coat, standing in a snowy forest, full body, cinematic lighting",
    "negative_prompt": "blurry, low quality, watermark, text",
    "kind": "reference",
    "mode": "icon",
    "output_size": 64,
    "image_size": 1024,
    "image_width": 832,
    "image_height": 1216,
    "seed": 2024,
    "steps": 30,
    "cfg": 7.0,
    "lora_strength": 0.0,
    "transparent": False,
    "postprocess": "quantize",
    "palette_colors": 0,
    "resize_filter": "nearest",
    "candidates": 1,
    "checkpoint": "ponyDiffusionV6XL_v6StartWithThisOne.safetensors",
    "lora": "",
    "translate_prompt": False,
    "reference_images": [{"asset_id": "sample_portrait", "strength": 0.6, "focus": "face"}],
    "identity_engine": "none",
}

job = client.post("/api/generate", json=payload).json()["job_id"]
for _ in range(300):
    time.sleep(2)
    state = client.get(f"/api/jobs/{job}").json()
    if state["status"] in {"completed", "error", "cancelled"}:
        print("status:", state["status"], "| err:", (state.get("error") or "")[:200])
        print("prompt used:", (state.get("prompt_used") or "")[:120])
        print("warnings:", state.get("result", {}).get("warnings") if state.get("result") else None)
        print("job:", job)
        break
