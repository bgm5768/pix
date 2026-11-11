"""Check the proxied nk studio API (POST + image) from PixelForge."""

import sys

import httpx

sys.stdout.reconfigure(encoding="utf-8")

client = httpx.Client(base_url="http://127.0.0.1:8765", timeout=180)

status = client.get("/studio/api/status")
print("status:", status.status_code, "runner:", status.json().get("runner", {}).get("mode"))

episodes = client.get("/studio/api/episodes")
print("episodes:", episodes.status_code, str(episodes.text)[:200])

check = client.post(
    "/studio/api/check",
    json={"root": "0", "ep": "chi_ep0", "text": "테스트 문장입니다", "flow": ""},
    headers={"X-NK": "1"},
)
print("check:", check.status_code, str(check.text)[:220])

image = client.get("/studio/img", params={"p": "episodes/chi_ep0/auto/review.png", "w": "400"})
print("img:", image.status_code, image.headers.get("content-type"), len(image.content), "bytes")
