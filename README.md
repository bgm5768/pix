# PixelForge Local

로컬 ComfyUI + SDXL로 텍스트 프롬프트에서 **픽셀아트 스프라이트**와 **일반 이미지**를 만드는 Windows 전용 앱입니다.
외부 이미지 생성 API를 사용하지 않으며, 모든 생성은 이 PC의 GPU에서 실행됩니다.

- **페이지**: 상단의 `픽셀 생성기` / `이미지 생성기` 탭으로 전환
- **이미지 생성**: SDXL 원본 PNG를 512 / 768 / 1024px로 저장 (픽셀 후처리 없음, 기본 무검열 LUSTIFY! v2.0)
- **페이지별 모델**: 픽셀 페이지에는 pixel/sprite 계열, 이미지 페이지에는 SDXL 일반 모델만 표시
- **이미지 LoRA**: `sexy` 슬라이더 LoRA 선택 시 트리거 단어를 이미지 프롬프트에 자동 추가
- **입력**: 텍스트 프롬프트 (한국어/영어 모두 가능)
- **모드**: 아이콘 / 캐릭터 / 게임 오브젝트 / 타일·배경
- **출력**: 16 / 32 / 64 / 96 / 128px 실제 크기 PNG
- **프롬프트 구조화**: 한국어 요청 → 피사체/시점/구도/배경/팔레트 구조화, Ollama가 있으면 로컬 LLM 사용
- **투명 배경**: 패딩 rembg(u2net) + 단색 배경 색상 키 + 주 피사체 선택
- **구도 보정**: 피사체 bbox 추출 → 중앙 배치 → 목표 채움(75~85%) → 리사이즈
- **후보 자동 선택**: 픽셀 페이지에서 기본 4개 시드를 생성해 카드/패널·중복·구도 점수가 가장 높은 후보 선택
- **모델 선택/다운로드**: 설정 화면에서 체크포인트·LoRA를 드롭다운으로 바로 교체하고,
  SDXL 호환 모델을 내려받아 설치할 수 있음
- **모델 표시**: 현재 체크포인트/LoRA와 ComfyUI에 등록된 모델 수를 설정 화면에 표시
- **비교**: AI 원본 / 배경 제거 / 자동 크롭 / 최종 도트를 나란히 표시
- **자동 검증**: 중앙 배치, 피사체 크기, 단일 오브젝트, 카드/패널, 잘림, 알파, 출력 크기, NN 경계 확인
- **미리보기**: 픽셀은 nearest-neighbor 확대 + 체커보드, 이미지는 원본 비율 유지
- **저장**: 픽셀은 실제 크기 그대로, 이미지는 선택한 512/768/1024px 원본 PNG
- **UI**: React + TypeScript + Vite, 공통 패널 컴포넌트를 픽셀/이미지 두 페이지에서 재사용
- **서버**: FastAPI + Pillow + NumPy, DB 없음

![PixelForge Local 데모](docs/demo_64.png)

![PixelForge Local UI](docs/ui_result.png)

---

## 1. 요구 사항

| 항목 | 권장 |
|---|---|
| OS | Windows 10/11 |
| GPU | NVIDIA RTX 3080 Ti 12GB (검증 환경). 8GB 이상 권장 |
| ComfyUI | 기존 ComfyUI Desktop(standalone) 설치 |
| Python | 3.11–3.13 (검증: 3.11.9, 백엔드용 시스템 Python) |
| Node.js | 20+ (프론트엔드 빌드용) |
| 기본 모델 | 픽셀: SDXL 1.0 base + pixel-art-xl LoRA · 이미지: LUSTIFY! v2.0 (+ sexy LoRA 선택) |

> `start.bat`은 설치된 Python 중 3.11 → 3.12 → 3.13 순서로 선택합니다.
> 최신 Python(예: 3.15)은 고정된 패키지 wheel 호환성 때문에 사용하지 않습니다.

현재 프로젝트의 `config/settings.yaml`은 이 PC의 ComfyUI Desktop 설치 경로에 맞춰져 있습니다.
다른 PC에서 사용할 때는 아래 경로를 수정하세요.

```yaml
comfyui:
  install_dir: 'C:\Users\<사용자>\AppData\Local\Comfy-Desktop\ComfyUI-Installs\ComfyUI'
  python_path: '...\ComfyUI\.venv\Scripts\python.exe'
  main_path: '...\ComfyUI\main.py'
  models_dir: 'C:\Users\<사용자>\AppData\Local\Comfy-Desktop\ComfyUI-Shared\models'
```

---

## 2. 빠른 시작

1. `start.bat`을 더블클릭합니다.
2. 처음 실행 시 자동으로:
   - `backend/.venv` 생성
   - `backend/requirements.txt` 설치
   - `frontend/dist`가 없으면 `npm install` + `npm run build`
   - FastAPI 서버를 `http://127.0.0.1:8765`에서 시작
   - 브라우저 자동 열기
3. ComfyUI가 꺼져 있으면 기존 ComfyUI 설치를 자동으로 기동합니다.
   (자동 기동이 싫으면 `config/settings.yaml`의 `comfyui.auto_start: false`)
4. 상단에서 **픽셀 생성기** 또는 **이미지 생성기** 페이지를 고릅니다.
5. 프롬프트를 입력하고 **도트 생성** 또는 **이미지 생성**을 누릅니다.

> `start.bat`은 이미 백엔드가 실행 중이면 중복 실행하지 않고 브라우저만 엽니다.

### 수동 실행

```bat
cd /d C:\workspace\pix
backend\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

백엔드 작업 디렉터리는 `backend`여야 합니다.

```bat
cd /d C:\workspace\pix\backend
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

프론트엔드 개발 모드:

```bat
cd /d C:\workspace\pix\frontend
npm run dev
```

Vite 개발 서버(`http://127.0.0.1:5173`)는 `/api`, `/files`를 8765로 프록시합니다.

### GitHub Pages에서 사용하기 (로컬 GPU 유지)

배포된 UI: <https://bgm5768.github.io/pix/>

GitHub Pages는 **정적 UI만** 호스팅합니다. 이미지 생성은 여전히 이 PC의
`start.bat` → FastAPI(`http://127.0.0.1:8765`) → ComfyUI + RTX GPU에서 실행됩니다.
따라서 Pages 화면은 **백엔드가 실행 중인 같은 PC의 Chrome/Edge**에서 열어야 합니다.
다른 PC나 휴대폰에서 열면 `127.0.0.1`이 그 기기를 가리키므로 연결되지 않습니다.

1. 이 PC에서 `start.bat`을 실행해 백엔드와 ComfyUI를 켭니다.
2. 같은 PC에서 <https://bgm5768.github.io/pix/>를 엽니다.
3. 브라우저가 로컬 네트워크 접근 권한을 물으면 **허용**합니다.
   (Chrome/Edge의 Private Network Access 정책)
4. 상단에서 `이미지 생성기`를 고르고 프롬프트를 입력합니다.
   체크포인트/LoRA 선택과 실제 생성 요청은 로컬 백엔드로 전달됩니다.

배포는 `gh-pages` 브랜치에 정적 빌드 결과를 올리는 방식입니다. UI를 수정한 뒤
`scripts/deploy_pages.bat`을 실행하면 `/pix/` base 빌드와 `gh-pages` 푸시가 한 번에 됩니다.
GitHub 저장소의 **Settings → Pages** 소스는 `gh-pages` 브랜치의 `/ (root)`로 설정되어 있습니다.

```bat
cd /d C:\workspace\pix\frontend
npm run build:pages
```

Pages 빌드는 `.env.pages`의 `VITE_API_BASE=http://127.0.0.1:8765`를 사용합니다.
백엔드는 `config/settings.yaml`의 `app.cors_origins`에 등록된
`https://bgm5768.github.io`를 허용하고, Private Network Access 응답 헤더를 함께 보냅니다.

![GitHub Pages에서 로컬 GPU로 생성한 이미지](docs/pages_image_result.jpg)

**배포 검증 (2026-11-11)**: `https://bgm5768.github.io/pix/`에서 LUSTIFY! v2.0 +
1024×1024 + 28 steps로 이미지를 생성했습니다. 작업 ID `660e2451930d`, **11.6초**,
원본 1,580,103 bytes, 다운로드 `200 image/png`를 확인했습니다.
Pages UI → CORS preflight `200` → 로컬 백엔드/ComfyUI → RTX 3080 Ti 경로가
HTTPS 페이지에서 그대로 동작합니다. 픽셀 페이지도 Pages UI에서 모델 목록/갤러리가
정상 로드되고 콘솔 오류가 없음을 확인했습니다.

> HTTPS Pages에서 `http://127.0.0.1`로 접속하는 것은 루프백 예외로 허용되지만,
> 브라우저 버전/보안 정책에 따라 차단될 수 있습니다. 연결이 되지 않으면 최신
> Chrome/Edge에서 로컬 네트워크 권한을 허용하고, 그래도 안 되면 Cloudflare Tunnel
> 같은 HTTPS 터널로 백엔지를 노출한 뒤 `.env.pages`의 주소를 바꿔 다시 빌드하세요.

---

## 3. 모델 준비

### 3.1 SDXL 1.0 base

- 파일: `sd_xl_base_1.0.safetensors` (약 6.46GB)
- 다운로드:
  <https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors>
- 저장 위치:
  `C:\Users\<사용자>\AppData\Local\Comfy-Desktop\ComfyUI-Shared\models\checkpoints\`
- 이 파일은 픽셀 페이지의 기본 체크포인트입니다. 이미지 페이지에서도 선택할 수 있지만,
  이미지 페이지의 기본값은 아래 LUSTIFY! v2.0입니다. `NoobAI-XL` 같은 SDXL 호환 모델도
  이미지 페이지 목록에 표시됩니다.

### 3.2 LUSTIFY! v2.0 + sexy LoRA (이미지 페이지)

이미지 페이지에는 무검열 포토리얼 SDXL 체크포인트를 기본으로 연결해 두었습니다.

- 체크포인트: `lustifySDXLNSFWSFW_v20.safetensors` (약 6.46GB)
  - Civitai `LUSTIFY! [SDXL NSFW & SFW checkpoint]` v2.0 (모델 573152 / 버전 708635)
  - Hugging Face 미러: <https://huggingface.co/shootstuff/LUSTIFY-v2.0>
  - SDXL 1.0 기반, 자연어 프롬프트, NSFW/SFW 모두 지원
- LoRA: `sexy.safetensors` (약 8.4MB, MIT)
  - <https://huggingface.co/ntc-ai/SDXL-LoRA-slider.sexy>
  - SDXL 1.0 기반 NSFW 강도 슬라이더, 트리거 `sexy`
  - 권장 강도 1.2 (UI에서 0~3 조절 가능)

> **프롬프트 검열에 대해**: 이 앱과 로컬 ComfyUI에는 프롬프트 키워드 필터가 없습니다.
> 이미지 페이지의 프롬프트는 가공 없이 그대로 ComfyUI에 전달되며, 결과의 검열 여부는
> 전적으로 체크포인트 가중치에 달려 있습니다. 위 체크포인트는 NSFW 프롬프트를 거부하도록
> 학습되지 않은 모델입니다. LoRA의 `sexy` 트리거는 검열 우회가 아니라 LoRA를 활성화하는
> 단어이며, LoRA를 선택하면 이미지 프롬프트 끝에 자동으로 추가됩니다(픽셀 페이지는 제외).

> **라이선스/사용 제한**: LUSTIFY v2.0의 Civitai 설정은 `allowCommercialUse: [RentCivit, Image]`,
> `allowNoCredit: false`, 파생 모델 허용입니다. 생성 이미지를 상업적으로 쓸 때는 제작자
> 크레딧을 표시해야 하며, 모델 파일 자체의 재배포 조건은 원본 모델 카드를 따릅니다.
> 성인 콘텐츠는 법적 성인만, 실제 인물·미성년자와 무관한 로컬 생성에만 사용하세요.

### 3.3 pixel-art-xl LoRA

- 파일: `pixel-art-xl.safetensors` (약 159MB)
- 다운로드:
  <https://huggingface.co/nerijs/pixel-art-xl/resolve/main/pixel-art-xl.safetensors>
- 저장 위치:
  `C:\Users\<사용자>\AppData\Local\Comfy-Desktop\ComfyUI-Shared\models\loras\`

### 3.4 화면에서 다른 모델 받기 · 교체

설정 패널의 **MODEL STACK**에서 바로 바꿀 수 있습니다.

- **CHECKPOINT / LoRA 드롭다운**: ComfyUI에 등록된 모델을 즉시 선택합니다.
  선택값은 브라우저에 저장되고 다음 생성 요청에 `checkpoint` / `lora`로 전달됩니다.
  픽셀 페이지에는 파일명에 `pixel`, `sprite`, `dot`, `8bit`, `retro` 등이 포함된 모델만,
  이미지 페이지에는 그 외 SDXL 호환 일반 모델만 표시됩니다. 페이지별 선택값은 따로 저장됩니다.
- **모델 받기**: 아래 curated 목록에서 `받기`를 누르면 ComfyUI 모델 폴더로 바로 다운로드합니다.
  진행률·속도가 표시되고, 완료 후 목록에 자동으로 추가됩니다.
- LoRA를 쓰지 않으려면 LoRA 드롭다운에서 `사용 안 함`을 선택합니다.
- `hunyuan3d`, `sam3.1`처럼 SDXL 텍스트→이미지용이 아닌 파일은 두 페이지 모두에서 제외됩니다.

기본 제공 다운로드 목록:

| 종류 | 모델 | 크기 |
|---|---|---|
| 체크포인트 | PixelArtDiffusionXL · SpriteShaper | 약 6.46GB |
| 체크포인트 | LUSTIFY! v2.0 (무검열 이미지 기본) | 약 6.46GB |
| LoRA | PixelArtRedmond · Lite64 | 약 163MB |
| LoRA | Pixel Art SDXL DoRA v0.9 | 약 357MB |
| LoRA | Pixel Art LoRA SDXL | 약 177MB |
| LoRA | NTC Slider · sexy (이미지용, 트리거 `sexy`) | 약 8.4MB |

`config/settings.yaml`의 `generation.checkpoint` / `generation.lora`는 화면에서 아무것도
선택하지 않았을 때 사용하는 기본값입니다. 이미지 페이지는 `generation.image_checkpoint` /
`generation.image_lora` / `generation.default_image_size` / `generation.image_default_candidates`를
사용합니다.

> 다운로드 모델의 라이선스는 각 Hugging Face 저장소(모델 카드)를 확인하세요.
> 이 프로젝트는 로컬 추론만 하며 모델 파일을 재배포하지 않습니다.

### 3.5 배경 분리 모델 (rembg)

투명 배경을 켜면 로컬 `rembg`가 u2net 모델을 사용합니다.
첫 실행 시 자동으로 다운로드됩니다(약 176MB).

```
C:\Users\<사용자>\.rembg\models\u2net\u2net.onnx
```

픽셀아트 아이콘이 프레임을 가득 채우면 u2net이 배경을 구분하지 못하는 경우가 있어,
가장자리 색으로 이미지를 패딩한 뒤 분리합니다. 분리된 마스크는 테두리 단색 색상 키와
결합해 스프라이트 시트 이음선을 제거하고, 가장 큰 주 피사체만 남깁니다.
인터넷이 없거나 모델 다운로드에 실패하면 내장된 색상 플러드필 방식으로 자동 대체되고,
UI에 경고가 표시됩니다. `config/settings.yaml`에서 `generation.rembg_enabled: false`로 끌 수도 있습니다.

---

## 4. 사용 방법

상단의 두 탭은 각각 독립된 프롬프트·설정·결과·갤러리를 가집니다. 페이지를 바꿔도
진행 중인 작업과 선택한 모델은 유지됩니다.

### 4.1 픽셀 생성기

1. **POSITIVE PROMPT**에 만들고 싶은 캐릭터/오브젝트를 입력합니다.
   예: `도서관 아이콘 만들어줘`, `귀여운 고양이 캐릭터 한 명 만들어줘`
2. **ASSET MODE**에서 아이콘 / 캐릭터 / 게임 오브젝트 / 타일·배경을 선택합니다.
   아이콘·캐릭터·오브젝트 모드는 단일 피사체만 남기고, 타일 모드만 반복 배경을 허용합니다.
   설정 패널 상단의 **MODEL STACK**에서 현재 체크포인트/LoRA를 확인하고 드롭다운으로
   바로 교체할 수 있습니다. `모델 받기` 목록에서 새 SDXL 모델도 내려받을 수 있습니다.
   LoRA를 끄려면 LoRA 드롭다운에서 `사용 안 함`을 선택합니다.
3. **NEGATIVE PROMPT**는 기본값을 그대로 두는 것을 권장합니다.
4. **OUTPUT RESOLUTION**에서 16/32/64/96/128px를 선택합니다.
5. 필요하면 Seed, Steps, CFG, LoRA Strength, Post-process, 팔레트 색상,
   Resize Filter, 투명 배경을 조정합니다.
6. **도트 생성**을 누릅니다.
7. 결과 패널에서:
   - AI 원본(512×512) / 배경 제거 / 자동 크롭 / 최종 도트를 비교
   - 자동 검증 결과(중앙 배치, 피사체 크기, 단일 오브젝트, 잘림, 알파 등) 확인
   - 실제 픽셀 크기와 팔레트 색상 수 확인
   - **PNG 저장**으로 실제 크기 PNG 다운로드
   - **다시 생성**으로 새 시드 재생성
8. 최근 결과는 오른쪽 **ARCHIVE** 갤러리에 저장되며, 클릭하면 다시 볼 수 있습니다.

### 4.2 이미지 생성기

1. 상단에서 **이미지 생성기** 탭을 누릅니다.
2. **POSITIVE PROMPT**에 원하는 장면을 자연어로 입력합니다.
   예: `a lone lighthouse on a rocky cliff at sunset, cinematic lighting, highly detailed, wide shot`
3. 필요하면 **NEGATIVE PROMPT**를 수정합니다. 이미지 페이지의 기본 네거티브는
   인물 해부/저품질/워터마크 위주이며 픽셀 전용 문구가 포함되지 않습니다.
4. **IMAGE RESOLUTION**에서 512 / 768 / 1024px를 선택합니다. 1024px가 가장 선명합니다.
5. **MODEL STACK**에서 이미지용 체크포인트를 선택합니다. 기본값은 `LUSTIFY! v2.0`이며
   `NoobAI-XL`, `SDXL base`로 바꿀 수 있습니다. 픽셀 전용 체크포인트/LoRA는 목록에
   나타나지 않습니다. LoRA를 고르면 트리거 단어가 프롬프트에 자동 추가되고, 쓰지 않으려면
   `사용 안 함`을 선택합니다.
6. **이미지 생성**을 누릅니다. 후보는 1개만 생성됩니다.
7. 결과 패널에서 SDXL 원본 PNG를 확인하고 **PNG 저장**으로 내려받습니다.
8. 최근 이미지는 오른쪽 **이미지 갤러리**에 저장되며, 클릭하면 다시 볼 수 있습니다.

이미지 페이지는 다음을 적용하지 않습니다.

- 픽셀아트 프롬프트 자동 래핑 및 픽셀 전용 네거티브
- 배경 제거 / 자동 크롭 / 팔레트 양자화 / nearest-neighbor 축소
- 후보 자동 선택과 자동 검증

즉 SDXL이 만든 원본을 그대로 보존하며, 후처리 단계 없이 저장합니다. 픽셀 결과와 이미지
결과는 서로 다른 폴더(`outputs/pixel_art`, `outputs/images`)에 저장되어 섞이지 않습니다.

### 권장 설정 (픽셀 생성기)

| 설정 | 값 |
|---|---|
| Base resolution | 512×512 (고정) |
| Sampler | DPM++ 2M Karras |
| Steps | 28 |
| CFG | 6.0 |
| LoRA strength | 0.8 |
| Output | 64px (기본), 32/64/128px 검증 완료 |
| Candidates | 4 (기본, API에서 1~8 조정 가능, 타일은 자동 1) |
| Post-process | quantize (권장) |
| Palette | 32px=16색, 64px=24색, 128px=32색 (또는 원본 색상) |
| Resize filter | nearest (기본), box / lanczos 비교 가능 |

- `quantize`: 제한 팔레트로 양자화 → 가장 픽셀아트다운 결과
- `nearest`: 다운스케일만 하고 색을 줄이지 않음 → 원본 느낌, 16px에서는 거칠 수 있음
- `posterize`: 색 단계를 단순화 → 강한 단순화
- 팔레트 `원본 색상`(0): 양자화하지 않고 원본 색을 유지합니다.
- 최종 미리보기는 항상 nearest-neighbor로 확대됩니다. 타일 모드는 box가 자동 적용됩니다.

> 자동 검증이 실패해도 결과를 삭제하거나 덮어쓰지 않습니다. 원본은 항상 보존되며,
> 경고와 미리보기를 보고 사용자가 직접 판단할 수 있습니다.

---

## 5. 동작 구조

```
[React UI · 픽셀 생성기 / 이미지 생성기]
   │ POST /api/generate { kind: "pixel" | "image", ... }
   ▼
[FastAPI JobManager] ── 1개 활성 + 최대 2개 대기 ──▶ [ComfyUI HTTP/WebSocket]
   │                                                   │
   │                                                   ├─ CheckpointLoaderSimple (SDXL)
   │                                                   ├─ LoraLoader (선택 사항)
   │                                                   ├─ CLIPTextEncode (positive/negative)
   │                                                   ├─ EmptyLatentImage 512×512 또는 512/768/1024²
   │                                                   ├─ KSampler (dpmpp_2m + karras, 28 steps, CFG 6)
   │                                                   ├─ VAEDecode
   │                                                   └─ SaveImage
   │                                        (pixel: 후보 1..N, seed = base_seed + index)
   │                                        (image: 후보 1, 원본 프롬프트 그대로)
   ▼
   ├─ kind=pixel → [Pillow/NumPy 후처리]
   │    ├─ 패딩 rembg u2net 배경 분리 + 테두리 색상 키
   │    ├─ 주 피사체 컴포넌트 선택 (중복/스프라이트 시트 제거)
   │    ├─ 카드/패널 점수 + 자동 검증 점수로 최선 후보 선택
   │    ├─ 피사체 bbox 추출 + 중앙 배치 + 목표 채움(75~85%)
   │    ├─ premultiplied alpha 리사이즈 (nearest/box/lanczos)
   │    ├─ 제한 팔레트 양자화 + 약한 despeckle
   │    ├─ 자동 검증 (중앙/크기/단일/카드 패널/잘림/알파/출력 크기/NN 경계)
   │    └─ nearest-neighbor 미리보기 (512px)
   │
   └─ kind=image → 후처리 없이 원본 PNG + 축소 미리보기 저장
   ▼
outputs/
   ├─ originals/<job>_original.png           (선택된 AI 원본 512×512 RGB)
   ├─ candidates/<job>_c<index>.png          (픽셀/이미지 후보 원본)
   ├─ cutouts/<job>_cutout.png               (픽셀: 배경 제거 결과)
   ├─ crops/<job>_crop.png                   (픽셀: 피사체 자동 크롭)
   ├─ pixel_art/<job>_pixel_<size>.png       (픽셀: 최종 RGBA/RGB)
   ├─ previews/<job>_preview_<size>.png      (픽셀: nearest 확대)
   ├─ images/<job>_image_<size>.png          (이미지: SDXL 원본 PNG)
   ├─ image_previews/<job>_image_preview_<size>.png (이미지: 갤러리용 축소본)
   └─ metadata/<job>.json                    (프롬프트/모델/시드/설정/후보 점수/검증/결과)
```

- 원본과 최종 결과를 **별도 파일**로 보존합니다.
- 픽셀 결과는 투명 모드에서 binary alpha를 쓰는 RGBA PNG, 불투명 모드에서 RGB PNG입니다.
- 이미지 결과는 항상 RGB PNG이며, `kind: "image"`와 `image_size`가 메타데이터에 기록됩니다.
- ComfyUI WebSocket으로 진행률을 받고, 완료는 `/history/{prompt_id}` 폴링으로 확인합니다.
- ComfyUI가 꺼져 있으면 작업 시작 전에 `ComfyLauncher`가 기존 설치를 자동 기동합니다.

---

## 6. API

백엔드는 `http://127.0.0.1:8765`에서 실행됩니다.

| Method | Path | 설명 |
|---|---|---|
| POST | `/api/generate` | 생성 작업 제출 (`kind`로 픽셀/이미지 선택) |
| GET | `/api/jobs/{job_id}` | 작업 상태/진행률/결과 조회 |
| POST | `/api/jobs/{job_id}/cancel` | 작업 취소 |
| GET | `/api/outputs?limit=30&kind=pixel` | 최근 결과 목록 (`kind=pixel` 기본, `kind=image`) |
| GET | `/api/health` | 백엔드/ComfyUI/GPU/모델/큐 상태 |
| GET | `/api/models/catalog` | 다운로드 가능한 모델과 설치/진행 상태 |
| POST | `/api/models/downloads/{id}` | 모델 다운로드 시작 |
| POST | `/api/models/downloads/{id}/cancel` | 진행 중인 다운로드 취소 |
| GET | `/api/config` | UI 기본 설정(픽셀/이미지 기본값 포함) |
| GET | `/api/download/{job_id}?kind=pixel` | 결과 PNG 다운로드 (`kind=image`로 이미지 결과) |
| GET | `/files/...` | 원본/픽셀/이미지/미리보기 정적 파일 |

### 생성 예시

픽셀 생성:

```powershell
$body = @{
  kind = "pixel"
  prompt = "a tiny knight standing and holding a glowing sword, full body, feet visible, side view, game sprite, fantasy"
  mode = "character"
  output_size = 64
  seed = 987654321
  steps = 28
  cfg = 6.0
  lora_strength = 0.8
  transparent = $true
  postprocess = "quantize"
  palette_colors = 24
  resize_filter = "nearest"
  candidates = 4
  # 선택 사항: 요청별 모델 교체 (생략하면 settings.yaml 기본값)
  checkpoint = "SDXL1.0_PixelArtDiffusionXL_SpriteShaper.safetensors"
  lora = "pixel-art-xl.safetensors"
} | ConvertTo-Json

$job = Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/generate" `
  -Method Post -ContentType "application/json" -Body $body

Invoke-RestMethod "http://127.0.0.1:8765/api/jobs/$($job.job_id)"
```

이미지 생성:

```powershell
$body = @{
  kind = "image"
  prompt = "a lone lighthouse on a rocky cliff at sunset, cinematic lighting, highly detailed, wide shot"
  image_size = 1024
  seed = 123456789
  steps = 28
  cfg = 6.0
  checkpoint = "lustifySDXLNSFWSFW_v20.safetensors"
  lora = ""   # 예: "sexy.safetensors" (선택 시 프롬프트에 'sexy' 자동 추가)
} | ConvertTo-Json

$job = Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/generate" `
  -Method Post -ContentType "application/json" -Body $body

$result = Invoke-RestMethod "http://127.0.0.1:8765/api/jobs/$($job.job_id)"
$result.result.image_url      # /files/images/<job_id>_image_1024.png
$result.result.download_url   # /api/download/<job_id>?kind=image
```

`GET /api/jobs/{job_id}` 응답에는 다음 정보가 포함됩니다.

- `request.kind`, `request.image_size`: 요청한 페이지 종류와 이미지 해상도
- `result.kind`: `"pixel"` 또는 `"image"`
- `result.image_url`, `result.image_preview_url`: 이미지 페이지 결과 경로
- `prompt_plan`: 구조화된 프롬프트(피사체/시점/구도/배경/positive/negative/source, 이미지 모드는 `null`)
- `base_seed`: 사용자가 요청한 기준 시드
- `seed_used`: 실제 선택된 후보의 시드 (`base_seed + candidate_index`)
- `result.mode`, `result.subject_fill`, `result.resize_filter`
- `result.cutout_url`, `result.crop_url` (픽셀 결과)
- `result.candidates_generated`, `result.candidate_index`, `result.candidate_score`
- `result.panel_suspected`: 카드/패널/사각 배경 의심 여부
- `result.quality`: 자동 검증 항목별 통과 여부와 측정값 (이미지 모드는 빈 배열)
- `result.warnings`: 후보 선택, 중복 오브젝트 감지, 분리 실패, 검증 실패 안내

`GET /api/health`의 `models`에는 현재 기본 모델과 ComfyUI에서 사용 가능한 전체 목록이 포함됩니다.

- `models.checkpoint.name`, `models.lora.name`: `settings.yaml`의 기본 모델
- `models.checkpoints[]`, `models.loras[]`: `{ name, size_bytes, compatible, category }` 목록
- `category`: `pixel` / `image` / `other` — UI가 페이지별로 모델을 필터링하는 기준
- `compatible: false` 또는 `category: "other"`: SDXL 텍스트→이미지용이 아닌 파일 (두 페이지 모두 제외)
- 생성 요청에 `checkpoint` / `lora`를 넣으면 요청별로 모델을 바꿀 수 있습니다.
  `lora: ""`는 해당 요청에서 LoRA를 사용하지 않는다는 뜻입니다.
- `GET /api/models/catalog`에서 다운로드 가능한 모델·진행률·설치 여부를 확인합니다.
- `GET /api/config`에는 `default_image_size`, `image_sizes`, `image_checkpoint`, `image_lora`,
  `default_image_candidates`, `default_image_negative_prompt`가 추가로 포함됩니다.

### 오류 코드

| HTTP | code | 의미 |
|---|---|---|
| 422 | `VALIDATION_ERROR` | 프롬프트/해상도/시드 등 입력값 오류 |
| 404 | `JOB_NOT_FOUND` | 없는 작업 ID |
| 409 | `JOB_CONFLICT` | 이미 끝난 작업 취소 시도 |
| 409 | `MODEL_DOWNLOAD_ERROR` | 모델 다운로드 시작/취소 불가 또는 서버 거부 |
| 429 | `QUEUE_FULL` | 대기 작업 초과 (최대 2개) |
| 507 | `VRAM_OOM` | GPU VRAM 부족 |
| 502 | `COMFY_EXECUTION_ERROR` | ComfyUI 실행 오류 |
| 503 | `COMFY_CONNECTION_ERROR` | ComfyUI 연결 실패 |

---

## 7. 검증 결과 (RTX 3080 Ti 12GB)

2026-11-10에 필수 5개 프롬프트를 32/64/128px로 다시 생성했습니다.
**15개 작업 모두 완료, 15개 모두 단일 피사체, 자동 검증 10/10 통과, 카드/패널 0건**입니다.
각 작업은 후보 4개를 생성한 뒤 가장 높은 점수의 후보를 자동 선택했습니다.

| 케이스 | 모드 | 32px | 64px | 128px | 선택 후보 (32/64/128) |
|---|---|---|---|---|---|
| 도서관 아이콘 | icon | 81% / 10-10 | 78% / 10-10 | 79% / 10-10 | #4 / #4 / #4 |
| 귀여운 고양이 캐릭터 | character | 81% / 10-10 | 80% / 10-10 | 81% / 10-10 | #2 / #2 / #2 |
| 나무 한 그루 | object | 81% / 10-10 | 78% / 10-10 | 79% / 10-10 | #2 / #2 / #3 |
| 빨간색 사과 하나 | object | 75% / 10-10 | 78% / 10-10 | 77% / 10-10 | #1 / #2 / #2 |
| 작은 학교 건물 | icon | 81% / 10-10 | 80% / 10-10 | 80% / 10-10 | #1 / #1 / #1 |

- 표의 숫자는 `피사체 채움 / 자동 검증 통과`.
- 15개 작업 × 4후보 = 60개 후보를 생성했고, 전체 후보 평균 점수 83.96 대비
  선택된 후보 평균 점수는 **98.25**입니다. 60개 중 51개가 10/10이었습니다.
- 4후보 기준 평균 소요 시간은 **21.13초**(최소 19.48, 최대 23.52)입니다.
- 전체 비교 시트와 상세 수치: [`docs/quality_report_2026-11-10.md`](docs/quality_report_2026-11-10.md)
- 리사이즈 필터 비교: [`experiments/resize_compare_42b7eb87222b_64.png`](experiments/resize_compare_42b7eb87222b_64.png)

추가 검증:

- **UI 전체 흐름**: 프롬프트 입력 → 모드/팔레트/리사이즈 필터 선택 → 진행률 → 64px 결과
  → 원본/배경 제거/자동 크롭/최종 비교 → 자동 검증 패널 → PNG 저장 → 갤러리 선택
- **후보 자동 선택**: 결과 패널에 `후보 4개 중 #N` 표시, 선택된 후보의 시드와 점수를
  API/아카이브/메타데이터에 기록
- **단일 오브젝트 필터**: `빨간색 사과 네 개 만들어줘` 요청에서 2×2 스프라이트 시트를 감지해
  주 사과 하나만 선택하고 경고 표시
- **중복 사과 + 카드 패널**: 두 가지 시드 테스트 모두 후보 4개 중 카드가 없는 결과를
  자동 선택 (`5b830fe1700c` #3/4, `375ce732d118` #1/4, 둘 다 10/10)
- **카드/패널 감지**: 알파 사각형 비율 + 밝은 단색 영역 + 균일 테두리로 점수를 계산,
  0.42 이상이면 `no_card_panel` 실패 및 후보 순위 하락
- **타일 모드**: `픽셀아트 숲 배경 타일 만들어줘` 64px RGB, box 리사이즈, 검증 3/3, 후보 1개
- **원본 팔레트**: 팔레트 0 선택 시 양자화 없이 원본 색상 유지(1,392색)
- **ComfyUI 자동 기동**: ComfyUI 프로세스를 중지한 뒤 작업 제출 → 기존 설치를
  `--extra-model-paths-config`로 자동 기동 → 작업 완료
- **입력 오류**: 빈 프롬프트/잘못된 해상도/시드/CFG/스텝/팔레트/후처리 → 422
- **대기열 초과**: 4번째 빠른 제출 → 429 `QUEUE_FULL`
- **VRAM OOM 매핑**: CUDA OOM 메시지 → 507 `VRAM_OOM` + 한국어 안내

### 이미지 생성기 검증

2026-11-10에 새 이미지 페이지를 실제 ComfyUI/RTX 3080 Ti에서 검증했습니다.

- **이미지 생성**: `NoobAI-XL-v1.0.safetensors`, 512×512, 28 steps, 후보 1개 → **8.5초** 완료
  (작업 ID `a19348cdac1e`). `outputs/images`, `outputs/image_previews`, `outputs/metadata`에
  원본/미리보기/메타데이터가 저장됐고 결과 패널에 `SDXL NATIVE`로 표시됐습니다.
- **1024px 이미지**: 같은 모델로 1024×1024 재검증 → **13.7초** 완료
  (작업 ID `f11b8e26bd19`, 원본 1.21MB). `GET /api/download/...?kind=image` →
  `200 image/png`로 정상 다운로드됐습니다.
- **갤러리/다운로드**: 이미지 갤러리에 1개가 표시되고 클릭 시 결과가 복원됐습니다.
  `GET /api/download/a19348cdac1e?kind=image` → `200 image/png` (190,526 bytes).
- **출력 분리**: 같은 시점에 `GET /api/outputs?kind=pixel`은 194개, `?kind=image`는 1개를
  반환해 픽셀/이미지 목록이 섞이지 않았습니다.
- **페이지별 모델 필터**: 픽셀 페이지는 체크포인트 1개(SpriteShaper)와 LoRA 4개,
  이미지 페이지는 체크포인트 3개(LUSTIFY! v2.0, NoobAI-XL, SDXL base)와 LoRA 1개(`sexy`)가
  표시됐습니다. LUSTIFY! v2.0이 이미지 페이지 기본값으로 선택됩니다.
- **페이지 상태 분리**: 이미지 작업이 진행 중일 때 픽셀 페이지로 전환하면 픽셀 페이지는
  `IDLE` 상태와 활성화된 생성 버튼을 유지하고, 이미지 페이지로 돌아오면 진행률/완료 상태가
  그대로 표시됐습니다. 두 페이지의 프롬프트·결과·갤러리도 서로 섞이지 않았습니다.
- **픽셀 회귀**: `SpriteShaper` + `PixelArtRedmond-Lite64`, 32px 4후보 중 #3 선택,
  자동 검증 10/10, **27.0초** 완료 (작업 ID `5cecbea25214`). 페이지 상태 분리 리팩터링 후
  같은 설정으로 다시 검증해 10/10, 23.4초 완료(작업 ID `34eb5f103a79`)를 확인했습니다.
- 두 페이지 모두 브라우저 콘솔 에러 0건이었습니다.

### 무검열 모델 · LoRA 검증 (2026-11-11)

- **LUSTIFY! v2.0 + sexy LoRA**: 1024×1024, 28 steps, LoRA strength 1.2 → **13.0초** 완료
  (작업 ID `985aa3df1f55`). 원본 1.58MB, 미리보기 723KB,
  `GET /api/download/985aa3df1f55?kind=image` → `200 image/png`를 확인했습니다.
  `prompt_used`는 요청 끝에 `, sexy`가 자동 추가된 형태로 저장됐습니다.
- **LoRA 트리거**: `NoobAI-XL` + `sexy`, 512×512 (작업 ID `a46ea7247892`)에서도 트리거가
  자동 추가되고 결과/갤러리/다운로드가 정상 동작했습니다.
- **프롬프트 원문**: LoRA를 `사용 안 함`으로 둔 512×512 작업(`373a5ea5652b`)은 `prompt_used`가
  요청한 문장과 완전히 같았습니다. 이미지 페이지에는 키워드 필터나 치환이 없습니다.
- **모델 설치**: `LUSTIFY! v2.0` 6,938,043,264 bytes와 `sexy.safetensors` 8,789,076 bytes를
  앱의 `받기` 기능으로 내려받고 `/api/health`에 `category: image`로 등록되는 것을 확인했습니다.

> LUSTIFY! v2.0은 무검열 체크포인트이므로 성인 콘텐츠가 생성될 수 있습니다. 법적 성인만
> 사용하고, 실제 인물·미성년자와 무관한 로컬 생성에만 사용하세요.

> 픽셀 페이지에서 후보 4개 생성 시 첫 작업은 ComfyUI 모델 로딩 때문에 20초 안팎, 이후에도
> 후보 수만큼 시간이 늘어납니다. RTX 3080 Ti에서 4후보 평균 약 21초입니다.
> 이미지 페이지는 후보 1개 기준 512px 약 8.5초, 1024px 약 13.7초입니다.

---

## 8. 문제 해결

### "ComfyUI 연결을 기다리는 중"이 계속 표시됨

1. `logs/backend.log`, `logs/comfyui-server.log` 확인
2. `http://127.0.0.1:8188/system_stats`가 응답하는지 확인
3. ComfyUI Desktop을 직접 실행하거나 `config/settings.yaml`의 경로 확인
4. 포트 8188이 다른 프로그램에 의해 사용 중이면 해당 프로그램 종료 또는 `base_url` 변경

### 모델을 찾을 수 없음 (`MODEL_MISSING`)

- `sd_xl_base_1.0.safetensors` → `...\models\checkpoints\`
- `pixel-art-xl.safetensors` → `...\models\loras\`
- ComfyUI 재시작 후 `/api/health`의 `models`가 `available: true`인지 확인

### GPU VRAM 부족 (`VRAM_OOM`)

- 다른 GPU 작업(게임, 영상 편집, 다른 AI 도구) 종료
- ComfyUI 재시작으로 VRAM 정리
- Steps를 낮추거나(예: 20) 픽셀 페이지에서 더 작은 출력(16/32px) 사용
- 픽셀 페이지의 base resolution은 512×512로 고정되어 있습니다. 이미지 페이지는 512px부터
  시도하고 여유가 있으면 768/1024px를 사용하세요.

### 투명 배경이 이상함

- 프롬프트에 `full body`, `plain solid white background`, `no shadow` 등을 포함
- 한 번에 한 캐릭터만 요청
- 얇은 무기/장식은 rembg가 배경으로 오인해 제거할 수 있음
- UI 경고가 나오면 `postprocess`를 `quantize`로, `transparent`를 끄고 비교해 보세요.

### npm/Python을 찾을 수 없음

- Python: <https://www.python.org/downloads/> (설치 시 "Add python.exe to PATH")
- Node.js: <https://nodejs.org/> (20 LTS 이상)
- 설치 후 `scripts\check_environment.bat` 실행

### 백엔드 포트 8765가 이미 사용 중

`start.bat`은 이미 실행 중인 PixelForge를 감지하면 브라우저만 엽니다.
다른 프로그램이 8765를 사용 중이면 해당 프로그램을 종료하거나 `config/settings.yaml`의 `app.port`를 변경하세요.

---

## 9. 프로젝트 구조

```
pix/
├─ start.bat                       # 원클릭 실행
├─ scripts/
│  ├─ start.bat                    # venv/의존성/프론트 빌드/서버 시작
│  ├─ deploy_pages.bat             # /pix/ 빌드 후 gh-pages 브랜치 배포
│  └─ check_environment.bat        # Python/Node/ComfyUI/모델/GPU 점검
├─ backend/
│  ├─ requirements.txt
│  └─ app/
│     ├─ main.py                   # FastAPI 앱, 정적 파일, 오류 핸들러
│     ├─ config.py                 # settings.yaml 로더
│     ├─ routes/api.py             # API 엔드포인트
│     ├─ schemas/models.py         # Pydantic 모델
│     └─ services/
│        ├─ comfy_client.py        # ComfyUI HTTP/WS 클라이언트
│        ├─ comfy_launcher.py      # ComfyUI 자동 기동
│        ├─ job_manager.py         # 단일 워커 큐, 픽셀/이미지 분기, 진행률, 후처리 오케스트레이션
│        ├─ prompt_engine.py       # 한국어 구조화 프롬프트 + 선택적 Ollama
│        ├─ postprocess.py         # 피사체 추출/크롭/스케일/양자화/검증
│        ├─ model_catalog.py       # 체크포인트/LoRA 목록과 pixel/image/other 분류
│        ├─ model_downloads.py     # 모델 다운로드/이어받기/취소
│        ├─ outputs.py             # 픽셀/이미지 저장, 출력 목록, 다운로드
│        └─ errors.py              # 사용자 친화적 오류 타입
├─ config/
│  ├─ settings.yaml                # 실행 설정
│  └─ comfyui_model_paths.generated.yaml  # 자동 생성(ComfyUI 모델 경로)
├─ workflows/
│  └─ text_to_pixel.json           # ComfyUI API 워크플로
├─ frontend/
│  ├─ package.json
│  ├─ .env.pages                    # Pages 빌드용 로컬 백엔드 주소
│  ├─ vite.config.ts
│  └─ src/
│     ├─ App.tsx                    # 페이지 탭, 페이지별 프롬프트/설정/결과 상태
│     ├─ components/                # Header/Prompt/Settings/Status/Result/Gallery (kind variant)
│     ├─ api/client.ts
│     ├─ types.ts
│     └─ styles/global.css
├─ docs/
│  ├─ quality_report_2026-11-10.md # 필수 15개 결과/검증 리포트
│  ├─ pages_image_result.jpg      # GitHub Pages + 로컬 GPU 생성 검증 화면
│  └─ demo_64.png, ui_result.png
├─ outputs/
│  ├─ originals/                   # AI 원본
│  ├─ candidates/                  # 픽셀/이미지 후보 원본
│  ├─ cutouts/                     # 픽셀: 배경 제거 결과
│  ├─ crops/                       # 픽셀: 피사체 자동 크롭
│  ├─ pixel_art/                   # 픽셀: 최종 PNG
│  ├─ previews/                    # 픽셀: 확대 미리보기
│  ├─ images/                      # 이미지: SDXL 원본 PNG
│  ├─ image_previews/              # 이미지: 갤러리용 축소 미리보기
│  └─ metadata/                    # 작업 메타데이터 JSON
└─ logs/
   ├─ backend.log
   └─ comfyui-server.log
```

---

## 10. 제약 사항

- **로컬 전용**: `127.0.0.1`에만 바인딩됩니다. 인증/결제/공개 호스팅은 없습니다.
  GitHub Pages는 UI만 호스팅하며, 생성은 같은 PC의 로컬 백엔드/GPU에서 실행됩니다.
- **Pages 접속 범위**: `https://bgm5768.github.io/pix/`는 백엔드가 실행 중인 같은 PC에서만
  동작합니다. 다른 PC/모바일에서 쓰려면 HTTPS 터널과 별도 인증 구성이 필요합니다.
- **단일 사용자**: 동시에 1개 작업만 GPU에서 실행됩니다.
- **스프라이트 1개**: 애니메이션, 스프라이트 시트, 다중 뷰는 범위 밖입니다.
- **결과 편차**: SDXL + LoRA 특성상 시드/프롬프트에 따라 품질이 달라집니다.
- **얇은 소품**: rembg가 얇은 무기나 분리된 장식 일부를 제거할 수 있습니다.
  원본은 항상 보존되며 UI에서 비교할 수 있습니다.
- **스프라이트 시트 셀 배경**: 중복 오브젝트 요청에서 한 칸만 선택할 수 있습니다.
  셀 자체에 카드/패널 배경이 있으면 후보 선택이 이를 감지해 다른 후보를 고르고,
  모든 후보가 의심스러우면 경고를 표시합니다. 감지는 휴리스틱이므로 원본 비교를 권장합니다.
- **후보 생성 비용**: 기본 4후보 생성으로 단일 후보보다 약 2.4배 오래 걸립니다.
  `candidates`를 1로 낮추면 기존 속도로 돌아갑니다.
- **모델 라이선스**: SDXL 1.0(base)과 pixel-art-xl LoRA, LUSTIFY! v2.0, `sexy` LoRA의
  라이선스를 확인하고 사용하세요. LUSTIFY! v2.0 생성 이미지를 상업적으로 쓸 때는 제작자
  크레딧이 필요합니다(`allowNoCredit: false`). `sexy` LoRA는 MIT입니다.
- **성인 콘텐츠**: 이미지 페이지 기본 모델은 무검열 NSFW/SFW 체크포인트입니다. 법적 성인만
  사용하고, 실제 인물·미성년자와 무관한 로컬 생성에만 사용하세요.
- **이미지 페이지**: SDXL 원본을 그대로 저장하므로 픽셀 팔레트/배경 제거/자동 검증이 없습니다.
  후보도 1개만 생성되며, 결과는 `outputs/images`에 별도 보관됩니다.
- **모델 분류**: 파일명 키워드(`pixel`, `sprite`, `dot`, `8bit`, `retro` 등)로 페이지를
  나누므로, 이름에 해당 키워드가 없는 픽셀 모델은 픽셀 페이지 목록에 나타나지 않을 수 있습니다.
  API 요청에는 `checkpoint`를 직접 지정할 수 있습니다.

---

## 11. 참고

- ComfyUI: <https://github.com/comfyanonymous/ComfyUI>
- SDXL 1.0: <https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0>
- pixel-art-xl: <https://huggingface.co/nerijs/pixel-art-xl>
- rembg: <https://github.com/danielgatis/rembg>
