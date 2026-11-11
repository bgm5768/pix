"""Smoke test for the nk studio proxy inside PixelForge."""

import json
import sys
import time

import httpx

sys.stdout.reconfigure(encoding="utf-8")

client = httpx.Client(base_url="http://127.0.0.1:8765", timeout=180)

print("status:", json.dumps(client.get("/api/studio/status").json(), ensure_ascii=False))

response = client.post("/api/studio/start")
print("start:", response.status_code, response.text[:300])
time.sleep(2)

page = client.get("/studio/")
print("studio html:", page.status_code, len(page.content), "bytes")
text = page.text
print("rewrote api path:", '"/studio/api/status"' in text)
print("rewrote img path:", '"/studio/img?' in text)
print("rewrote label link:", 'href="/studio/label"' in text)
print("rewrote ab link:", 'href="/studio/ab"' in text)
print("title present:", "<title>" in text)

status = client.get("/studio/api/status")
print("studio api:", status.status_code, status.text[:220])
