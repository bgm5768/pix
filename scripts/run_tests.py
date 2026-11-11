import json, time, urllib.request, urllib.error, os

BASE = "http://127.0.0.1:8765/api"

def post(path, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(BASE + path, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

def get(path):
    with urllib.request.urlopen(BASE + path) as r:
        return json.loads(r.read())

tests = [
    ("도서관 아이콘 만들어줘", "icon"),
    ("귀여운 고양이 캐릭터 한 명 만들어줘", "character"),
    ("나무 한 그루 만들어줘", "icon"),
    ("빨간색 사과 하나 만들어줘", "icon"),
    ("작은 픽셀아트 학교 건물 만들어줘", "icon"),
]

sizes = [32, 64, 128]

for prompt, mode in tests:
    for size in sizes:
        payload = {
            "prompt": prompt,
            "mode": mode,
            "output_size": size,
            "steps": 28,
            "cfg": 6.0,
            "lora_strength": 0.8,
            "transparent": True,
            "postprocess": "quantize",
            "palette_colors": 24,
        }
        try:
            resp = post("/generate", payload)
            job_id = resp["job_id"]
            print(f"submitted {job_id} | {prompt} | {mode} | {size}")
        except Exception as e:
            print("submit error", e)
            continue
        # poll
        while True:
            time.sleep(2)
            job = get(f"/jobs/{job_id}")
            status = job["status"]
            if status in ("completed", "error", "cancelled"):
                print(f"  -> {status} {job.get('error') or ''}")
                if status == "completed":
                    r = job["result"]
                    print(f"     pixel={r['pixel_url']} cutout={r.get('cutout_url')} crop={r.get('crop_url')} palette={r['palette_colors']}")
                break
            if status == "generating":
                pass