"""Queue a small nk job through the PixelForge studio proxy and watch it run."""

import sys
import time

import httpx

sys.stdout.reconfigure(encoding="utf-8")

client = httpx.Client(base_url="http://127.0.0.1:8765", timeout=180)
headers = {"X-NK": "1"}

before = client.get("/studio/api/status").json()
print("queue before:", len(before.get("queue") or []))

job = client.post("/studio/api/job", json={"kind": "aifile", "root": "0"}, headers=headers)
print("queue job:", job.status_code, job.text[:200])

for _ in range(30):
    time.sleep(2)
    state = client.get("/studio/api/status").json()
    queue = state.get("queue") or []
    runner = state.get("runner") or {}
    recent = state.get("recent") or []
    if not queue and runner.get("job") is None:
        print("queue after:", len(queue), "| runner:", runner.get("mode"), runner.get("runner"))
        if recent:
            last = recent[0]
            print("last job:", last.get("id"), "|", str(last.get("note") or last.get("args"))[:90])
        break
else:
    print("still queued:", len(queue))
