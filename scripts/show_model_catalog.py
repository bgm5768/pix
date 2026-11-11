"""Print the checkpoint catalog the UI shows in the model picker."""

import sys

import httpx

sys.stdout.reconfigure(encoding="utf-8")

health = httpx.get("http://127.0.0.1:8765/api/health", timeout=60).json()
for model in health["models"]["checkpoints"]:
    print(
        f"{model['name'][:44]:46} base={str(model.get('base_model'))[:16]:18}"
        f" nsfw={model.get('nsfw')} steps={model.get('recommended_steps')}"
        f" cfg={model.get('recommended_cfg')} cat={model.get('category')}"
    )
    if model.get("features"):
        print("      features:", model["features"])
    if model.get("description"):
        print("      desc:", model["description"][:90])
