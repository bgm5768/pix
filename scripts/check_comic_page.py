"""Assemble two generated cuts into a comic page and export the PDF."""

import sys
import time

import httpx

sys.stdout.reconfigure(encoding="utf-8")

client = httpx.Client(base_url="http://127.0.0.1:8765", timeout=300)


def newest_cut() -> str:
    items = client.get("/api/outputs", params={"kind": "reference", "limit": 5}).json()["items"]
    if not items:
        raise SystemExit("no reference outputs")
    return items[0]["image_url"]


first = newest_cut()
second = newest_cut()
print("panels:", first, second)

response = client.post(
    "/api/comic/page",
    json={
        "layout": "2x1",
        "width": 1240,
        "height": 1754,
        "title": "테스트 페이지",
        "panels": [
            {"path": first, "text": "여기부터 시작이에요.", "position": "top"},
            {"path": second, "text": "다음 컷에서는 더 큰 소식이 기다리고 있습니다.", "position": "bottom"},
        ],
    },
)
print("build:", response.status_code, response.text[:300])
page = response.json()
print("image:", page.get("image_url"), "| pdf:", page.get("pdf_url"))

pdf = client.get(page["pdf_url"])
print("pdf:", pdf.status_code, pdf.headers.get("content-type"), len(pdf.content), "bytes")

listing = client.get("/api/comic/pages").json()["items"]
print("pages listed:", len(listing), listing[0] if listing else None)
