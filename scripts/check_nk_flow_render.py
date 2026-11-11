"""Render one of the generated nk model workflows through ComfyUI.

This proves the generated flow files are valid API graphs and that the chosen
checkpoint actually draws, without needing nk's interactive policy prompt.
"""

import json
import sys
import time
from pathlib import Path

import httpx

sys.stdout.reconfigure(encoding="utf-8")

COMFY = "http://127.0.0.1:8188"
FLOW_DIR = Path(r"C:\nk\workflows")
TEST_PROMPT = "a girl with short hair wearing a red coat, snowy forest, cinematic lighting"


def fill(graph: dict, prompt: str, negative: str, seed: int) -> dict:
    filled = json.loads(json.dumps(graph))
    for node in filled.values():
        title = str((node.get("_meta") or {}).get("title") or "")
        inputs = node.get("inputs") or {}
        if title == "NK prompt":
            inputs["text"] = prompt
        elif title == "NK negative":
            inputs["text"] = negative
        elif title == "NK seed":
            inputs["seed"] = seed
        elif title == "NK lora":
            inputs["strength_model"] = 0.0
            inputs["strength_clip"] = 0.0
    return filled


def render(name: str) -> bool:
    path = FLOW_DIR / f"{name}.json"
    if not path.is_file():
        print(f"[skip] {name}: no flow file")
        return False
    graph = fill(json.loads(path.read_text(encoding="utf-8")), TEST_PROMPT, "worst quality, low quality", 4242)
    client = httpx.Client(timeout=300)
    response = client.post(f"{COMFY}/prompt", json={"prompt": graph, "client_id": "pixelforge-flow-test"})
    if response.status_code != 200:
        print(f"[FAIL] {name}: {response.status_code} {response.text[:200]}")
        return False
    prompt_id = response.json()["prompt_id"]
    for _ in range(240):
        time.sleep(2)
        history = client.get(f"{COMFY}/history/{prompt_id}")
        if history.status_code != 200:
            continue
        entry = history.json().get(prompt_id)
        if not entry:
            continue
        status = entry.get("status") or {}
        if status.get("status_str") == "error":
            print(f"[FAIL] {name}: {json.dumps(status)[:220]}")
            return False
        outputs = entry.get("outputs") or {}
        images = [
            image
            for node_output in outputs.values()
            for image in (node_output or {}).get("images", [])
        ]
        if images:
            print(f"[OK] {name}: rendered {images[0]['filename']}")
            return True
    print(f"[FAIL] {name}: timeout")
    return False


def main() -> int:
    names = sorted(p.stem for p in FLOW_DIR.glob("*.json"))
    if not names:
        print("no flow files")
        return 1
    target = sys.argv[1] if len(sys.argv) > 1 else names[0]
    ok = render(target)
    print("result:", "OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
