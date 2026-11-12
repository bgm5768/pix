"""End-to-end check of the nk studio: flow check and a real studio job."""

import json
import os
import subprocess
import sys
import time

import httpx

sys.stdout.reconfigure(encoding="utf-8")

API = "http://127.0.0.1:8765"
client = httpx.Client(base_url=API, timeout=600)

print("--- 1) studio status ---")
status = client.get("/api/studio/status").json()
print("policy_agreed:", status.get("policy_agreed"), "| running:", status.get("running"))

print("--- 2) nk flow check (nk CLI) ---")
kit = r"C:\nk"
for name in ["lustifySDXLNSFWSFW_v20", "ponyDiffusionV6XL_v6StartWithThisOne"]:
    result = subprocess.run(
        [sys.executable, "nk.py", "ep", "flow", "check", name],
        cwd=kit,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    tail = [line for line in (result.stdout or "").splitlines() if line.strip()][-3:]
    print(f"[{name}] rc={result.returncode}")
    for line in tail:
        print("   ", line)

print("--- 3) studio job (queue aifile) ---")
job = client.post("/studio/api/job", json={"kind": "aifile", "root": "0"}, headers={"X-NK": "1"})
print("queued:", job.status_code, job.text[:160])

for _ in range(40):
    time.sleep(2)
    state = client.get("/studio/api/status").json()
    queue = state.get("queue") or []
    runner = state.get("runner") or {}
    recent = state.get("recent") or []
    if not queue and runner.get("job") is None:
        print("runner:", runner.get("mode"), runner.get("runner"))
        if recent:
            print("last:", recent[0].get("id"), "|", str(recent[0].get("note"))[:70])
        break
else:
    print("still queued:", len(queue))
