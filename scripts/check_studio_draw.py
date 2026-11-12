"""Pick a model flow in the nk studio and draw a cut with it."""

import json
import sys
import time

import httpx

sys.stdout.reconfigure(encoding="utf-8")

API = "http://127.0.0.1:8765"
client = httpx.Client(base_url=API, timeout=900)
studio = "/studio"

print("--- 1) episodes ---")
episodes = client.get(f"{studio}/api/episodes").json()
for item in episodes[:5]:
    print("  ", item.get("ep"), "|", item.get("title"), "| pages:", item.get("pages"))
ep = episodes[0]["ep"]

print("--- 2) episode detail (cuts) ---")
detail = client.get(f"{studio}/api/ep", params={"ep": ep}).json()
cuts = detail.get("cuts") or []
print("  cuts:", len(cuts))
for cut in cuts[:4]:
    print("   ", {k: cut.get(k) for k in ("id", "scene", "roles", "flow") if k in cut})

print("--- 3) set the drawing flow to the LUSTIFY! model ---")
flow = "lustifySDXLNSFWSFW_v20"
result = client.post(
    f"{studio}/api/job",
    json={"kind": "setflow", "ep": ep, "flow": flow, "root": "0"},
    headers={"X-NK": "1"},
)
print("  setflow:", result.status_code, result.text[:160])

print("--- 4) queue a drawing job (3 candidates for cut 1) ---")
queued = client.post(
    f"{studio}/api/job",
    json={"kind": "cands", "ep": ep, "cut": 1, "root": "0"},
    headers={"X-NK": "1"},
)
print("  queued:", queued.status_code, queued.text[:160])

job_name = queued.json().get("name") if queued.status_code == 200 else None
deadline = time.time() + 900
while time.time() < deadline:
    time.sleep(3)
    state = client.get(f"{studio}/api/status").json()
    queue = state.get("queue") or []
    runner = state.get("runner") or {}
    if not queue and runner.get("job") is None:
        print("  finished. runner:", runner.get("mode"), runner.get("runner"))
        break
else:
    print("  timeout, still queued:", len(queue))

print("--- 5) recent jobs ---")
recent = client.get(f"{studio}/api/status").json().get("recent") or []
for item in recent[:4]:
    print("  ", item.get("id"), "|", str(item.get("note"))[:60], "| rc:", item.get("rc"))
