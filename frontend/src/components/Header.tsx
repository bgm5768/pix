import type { ReactNode } from "react";
import type { HealthResponse, JobView } from "../types";
import { formatVram } from "../utils";
import { CpuIcon, LinkIcon, PaletteIcon, PixelMark } from "./Icons";

interface HeaderProps {
  health: HealthResponse | null;
  healthError: string | null;
  job: JobView | null;
  checkpoint: string | null;
  lora: string | null;
}

type Tone = "good" | "warn" | "bad" | "neutral";

function StatusPill({
  tone,
  icon,
  label,
  detail,
}: {
  tone: Tone;
  icon: ReactNode;
  label: string;
  detail?: string;
}) {
  return (
    <div className={`status-pill tone-${tone}`} title={detail ?? label}>
      <span className="status-dot" />
      <span className="status-icon">{icon}</span>
      <span className="status-label">{label}</span>
    </div>
  );
}

function shortGpuName(name: string | undefined): string {
  if (!name) return "GPU 확인 불가";
  return name
    .replace("NVIDIA GeForce ", "")
    .replace(" : cudaMallocAsync", "")
    .replace(" : CUDA", "");
}

export function Header({ health, healthError, job, checkpoint, lora }: HeaderProps) {
  const connected = health?.comfyui.connected ?? false;
  const gpuBusy = Boolean(
    job && ["queued", "preparing", "generating", "postprocessing"].includes(job.status),
  );
  const selectedCheckpoint = checkpoint ?? health?.models.checkpoint.name ?? "";
  const selectedLora = lora === null ? (health?.models.lora.name ?? "") : lora;
  const checkpointInfo = health?.models.checkpoints.find(
    (item) => item.name === selectedCheckpoint,
  );
  const loraInfo = selectedLora
    ? health?.models.loras.find((item) => item.name === selectedLora)
    : null;
  const modelReady = Boolean(
    health && checkpointInfo?.compatible && (selectedLora === "" || loraInfo),
  );
  const comfyLabel = health
    ? connected
      ? `ComfyUI${health.comfyui.version ? ` v${health.comfyui.version}` : ""}`
      : "ComfyUI 연결 안 됨"
    : "백엔드 연결 중";
  const comfyDetail =
    healthError ?? health?.comfyui.error ?? health?.comfyui.url ?? "http://127.0.0.1:8188";
  const gpuLabel = gpuBusy ? "GPU 생성 중" : connected ? "GPU 대기" : "GPU 확인 불가";
  const gpuDetail = health?.gpu
    ? `${shortGpuName(health.gpu.name)} · VRAM ${formatVram(health.gpu.vram_free)} 여유 / ${formatVram(
        health.gpu.vram_total,
      )}`
    : "ComfyUI가 연결되면 GPU 정보를 표시합니다.";

  return (
    <header className="topbar">
      <div className="brand">
        <div className="brand-mark">
          <PixelMark size={38} />
        </div>
        <div className="brand-copy">
          <h1>
            PIXELFORGE <span>LOCAL</span>
          </h1>
          <p>LOCAL AI PIXEL ART FORGE · COMFYUI + SDXL</p>
        </div>
        <span className="local-badge">LOCAL ONLY</span>
      </div>

      <div className="topbar-status">
        <StatusPill
          tone={!health ? "neutral" : connected ? "good" : "bad"}
          icon={<LinkIcon size={15} />}
          label={comfyLabel}
          detail={comfyDetail}
        />
        <StatusPill
          tone={gpuBusy ? "warn" : health?.gpu ? "good" : "neutral"}
          icon={<CpuIcon size={15} />}
          label={gpuLabel}
          detail={gpuDetail}
        />
        <StatusPill
          tone={modelReady ? "good" : health ? "warn" : "neutral"}
          icon={<PaletteIcon size={15} />}
          label={modelReady ? "모델 준비됨" : "모델 확인 필요"}
          detail={
            health
              ? `체크포인트: ${selectedCheckpoint} (${checkpointInfo?.compatible ? "있음" : "없음"})\nLoRA: ${
                  selectedLora || "사용 안 함"
                } (${selectedLora === "" || loraInfo ? "있음" : "없음"})\nComfyUI 등록: 체크포인트 ${
                  health.models.checkpoints?.length ?? 0
                }개 / LoRA ${health.models.loras?.length ?? 0}개`
              : "모델 상태를 확인하는 중입니다."
          }
        />
      </div>
    </header>
  );
}
