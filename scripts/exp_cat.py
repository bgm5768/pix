import json, time, urllib.request, random

BASE = "http://127.0.0.1:8765/api"
def post(path, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(BASE + path, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())
def get(path):
    with urllib.request.urlopen(BASE + path) as r:
        return json.loads(r.read())

variants = [
    {"lora_strength":0.6,"steps":28,"cfg":6.0,"seed":111},
    {"lora_strength":0.8,"steps":32,"cfg":5.0,"seed":222},
    {"lora_strength":1.0,"steps":28,"cfg":7.0,"seed":333},
    {"lora_strength":0.7,"steps":24,"cfg":6.0,"seed":444},
]
for v in variants:
    payload = {
        "prompt":"귀여운 고양이 캐릭터 한 명 만들어줘",
        "mode":"character",
        "output_size":64,
        "transparent":True,
        "postprocess":"quantize",
        "palette_colors":24,
        "negative_prompt":"building, house, castle, cathedral, architecture, city, landscape, scenery, room, furniture, tree, ground, shadow, multiple characters, sprite sheet, multiple objects",
    }
    payload.update(v)
    resp = post("/generate", payload)
    job_id = resp["job_id"]
    print("submitted", job_id, v)
    while True:
        time.sleep(2)
        job = get(f"/jobs/{job_id}")
        if job["status"] in ("completed","error","cancelled"):
            print("  ->", job["status"], job.get("error") or "")
            if job["status"]=="completed":
                print("     ", job["result"]["pixel_url"])
            break
PY