# -*- coding: utf-8 -*-
"""Run one real generation and print quality/size metrics."""
from __future__ import annotations

import json
import time
import urllib.request

from PIL import Image
import numpy as np

BASE = "http://127.0.0.1:8765/api"
PROMPT = "도서관 아이콘 만들어줘"
MODE = "icon"
SIZE = 64
SEED = 1234567


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


payload = {
    "prompt": PROMPT,
    "mode": MODE,
    "output_size": SIZE,
    "seed": SEED,
    "steps": 28,
    "cfg": 6.0,
    "lora_strength": 0.8,
    "transparent": True,
    "postprocess": "quantize",
    "palette_colors": 16,
    "resize_filter": "nearest",
}
response = post("/generate", payload)
job_id = response["job_id"]
print("submitted", job_id)
while True:
    time.sleep(2)
    job = get(f"/jobs/{job_id}")
    print(job["status"], job["progress"], job["stage_message"])
    if job["status"] in {"completed", "error", "cancelled"}:
        break
if job["status"] != "completed":
    print(json.dumps(job, ensure_ascii=False, indent=2))
    raise SystemExit(1)

print("subject:", job["prompt_plan"]["subject"])
print("prompt:", job["prompt_used"])
result = job["result"]
print("result:", {key: result[key] for key in ("pixel_url", "crop_url", "subject_fill", "palette_colors", "resize_filter")})
for check in result["quality"]:
    print(f"  {check['passed']} {check['key']}: {check['value']}")

path = "C:/workspace/pix" + result["pixel_url"].replace("/files/", "/outputs/")
image = Image.open(path)
arr = np.array(image)
mask = arr[:, :, 3] > 0 if arr.ndim == 3 and arr.shape[2] == 4 else np.ones(arr.shape[:2], bool)
ys, xs = np.where(mask)
print("image:", image.mode, image.size, "bbox:", (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1), "opaque:", round(float(mask.mean()), 3))
