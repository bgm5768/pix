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

tests = [
    ("귀여운 고양이 캐릭터 한 명 만들어줘", "character"),
    ("작은 픽셀아트 학교 건물 만들어줘", "icon"),
    ("도서관 아이콘 만들어줘", "icon"),
]
for prompt, mode in tests:
    for size in [32, 64]:
        payload = {"prompt":prompt,"mode":mode,"output_size":size,"steps":28,"cfg":6.0,"lora_strength":0.8,"transparent":True,"postprocess":"quantize","palette_colors":24}
        resp = post("/generate", payload)
        job_id = resp["job_id"]
        print("submitted", job_id, prompt, size)
        while True:
            time.sleep(2)
            job = get(f"/jobs/{job_id}")
            if job["status"] in ("completed","error","cancelled"):
                print("  ->", job["status"], job.get("error") or "")
                if job["status"]=="completed":
                    r=job["result"]
                    print("     ", r["pixel_url"], "colors", r["palette_colors"])
                break
