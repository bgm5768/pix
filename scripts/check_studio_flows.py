"""List the nk model workflows PixelForge generated."""

import sys

import httpx

sys.stdout.reconfigure(encoding="utf-8")

client = httpx.Client(base_url="http://127.0.0.1:8765", timeout=180)
print("refresh:", client.post("/api/studio/flows/refresh").status_code)
for flow in client.get("/api/studio/flows").json()["items"]:
    print(f"  {flow['name']:44} {flow['steps']} steps / CFG {flow['cfg']}")
