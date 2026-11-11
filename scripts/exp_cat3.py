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

for ls in [0.0, 0.4]:
    payload = {
        "prompt": "a cute cat, full body, standing, front view, animal, game sprite",
        "mode": "character",
        "output_size": 64,
        "steps": 28,
        "cfg": 6.0,
        "lora_strength": ls,
        "transparent": True,
        "postprocess": "quantize",
        "palette_colors": 24,
        "negative_prompt": "building, house, castle, architecture, human, person",
    }
    resp = post("/generate", payload)
    job_id = resp["job_id"]
    print("submitted", job_id, "lora", ls)
    while True:
        time.sleep(2)
        job = get(f"/jobs/{job_id}")
        if job["status"] in ("completed","error","cancelled"):
            print("  ->", job["status"], job.get("error") or "")
            if job["status"]=="completed":
                print("     ", job["result"]["pixel_url"])
            break
PY