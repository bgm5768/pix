import json, time, urllib.request

BASE = "http://127.0.0.1:8765/api"
def post(path, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(BASE + path, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())
def get(path):
    with urllib.request.urlopen(BASE + path) as r:
        return json.loads(r.read())

payload = {
    "prompt": "pixel, a cute cat, full body, standing on four legs, side view, game sprite, transparent background",
    "mode": "character",
    "output_size": 64,
    "steps": 30,
    "cfg": 7.5,
    "lora_strength": 0.8,
    "transparent": True,
    "postprocess": "quantize",
    "palette_colors": 24,
    "seed": 42,
    "negative_prompt": "3d render, realistic, photograph, blurry, soft, smooth, anti-aliased, gradient, text, watermark, close-up, portrait, bust, cropped",
}
resp = post("/generate", payload)
job_id = resp["job_id"]
print("submitted", job_id)
while True:
    time.sleep(2)
    job = get(f"/jobs/{job_id}")
    if job["status"] in ("completed","error","cancelled"):
        print("  ->", job["status"], job.get("error") or "")
        if job["status"]=="completed":
            print("     ", job["result"]["pixel_url"])
        break
PY