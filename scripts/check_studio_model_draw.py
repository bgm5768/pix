"""Draw one nk cut with a chosen model flow through PixelForge's API."""

import sys

import httpx

sys.stdout.reconfigure(encoding="utf-8")

client = httpx.Client(base_url="http://127.0.0.1:8765", timeout=900)

print("--- episodes ---")
episodes = client.get("/studio/api/episodes").json()
for item in episodes[:4]:
    print("  ", item["ep"], "|", item["title"])

ep = "sap"
detail = client.get("/studio/api/ep", params={"ep": ep}).json()
print(f"--- {ep}: anima={detail.get('anima')} flow={detail.get('flow')!r} ---")
cut = next((c for c in detail["cuts"] if c["id"] == 2), detail["cuts"][0])
print("cut:", {k: cut.get(k) for k in ("id", "scene", "duo", "who")})

print("--- draw with LUSTIFY! ---")
response = client.post(
    "/api/studio/draw-cut",
    json={
        "ep": ep,
        "cut": cut["id"],
        "flow": "lustifySDXLNSFWSFW_v20",
        "seeds": "9101",
        "copy_to_candidates": True,
    },
)
print("status:", response.status_code)
data = response.json()
if response.status_code != 200:
    print(data)
    raise SystemExit(1)
print("output_dir:", data["output_dir"])
for item in data["items"]:
    print("  ", item["name"], "seed", item["seed"], "|", item["path"])
print("log:")
for line in (data.get("log") or "").splitlines()[-6:]:
    print("  ", line)

detail = client.get("/studio/api/ep", params={"ep": ep}).json()
updated = next((c for c in detail["cuts"] if c["id"] == cut["id"]), None)
print("candidates now:", [c["name"] for c in (updated or {}).get("cands", [])])
