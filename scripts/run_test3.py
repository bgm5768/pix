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

for prompt, mode in [("도서관 아이콘 만들어줘","icon"),("귀여운 고양이 캐릭터 한 명 만들어줘","character"),("작은 픽셀아트 학교 건물 만들어줘","icon")]:
    for size in [32]:
        payload = {"prompt":prompt,"mode":mode,"output_size":size,"transparent":True,"postprocess":"quantize","palette_colors":24}
        resp = post("/generate", payload)
        job_id = resp["job_id"]
        print("submitted", job_id, prompt)
        while True:
            time.sleep(2)
            job = get(f"/jobs/{job_id}")
            if job["status"] in ("completed","error","cancelled"):
                print("  ->", job["status"], job.get("error") or "")
                if job["status"]=="completed":
                    print("     ", job["result"]["pixel_url"], "prompt=", job["prompt_used"])
                break
PY