import type { GpuStatus, MemoryStatus, QueueStatus } from "../types";
import { formatVram } from "../utils";
import { CpuIcon } from "./Icons";

interface ResourceBarProps {
  gpu: GpuStatus | null;
  memory: MemoryStatus | null;
  queue: QueueStatus | null;
  connected: boolean;
}

function toneFor(percent: number): string {
  if (percent >= 92) return "hot";
  if (percent >= 75) return "warn";
  return "good";
}

function percentOf(used: number, total: number): number {
  if (!total || total <= 0) return 0;
  return Math.max(0, Math.min(100, (used / total) * 100));
}

function Meter({
  label,
  value,
  percent,
  detail,
  tone,
}: {
  label: string;
  value: string;
  percent: number;
  detail: string;
  tone: string;
}) {
  return (
    <div className="resource-item" title={detail}>
      <div className="resource-head">
        <span className="resource-label">{label}</span>
        <span className={`resource-value tone-${tone}`}>{value}</span>
      </div>
      <div className="resource-track">
        <div
          className={`resource-fill tone-${tone}`}
          style={{ width: `${Math.max(1, Math.min(100, percent))}%` }}
        />
      </div>
      <span className="resource-detail">{detail}</span>
    </div>
  );
}

export function ResourceBar({ gpu, memory, queue, connected }: ResourceBarProps) {
  const vramPercent = gpu ? percentOf(gpu.vram_used, gpu.vram_total) : 0;
  const gpuPercent = gpu?.utilization ?? 0;
  const ramPercent = memory?.percent ?? 0;
  const queueCount = (queue?.active ?? 0) + (queue?.pending ?? 0);
  const gpuDetail = gpu
    ? [
        `${formatVram(gpu.vram_used)} / ${formatVram(gpu.vram_total)} VRAM`,
        gpu.temperature_c != null ? `${Math.round(gpu.temperature_c)}°C` : null,
        gpu.power_w != null
          ? `${Math.round(gpu.power_w)}W${gpu.power_limit_w ? ` / ${Math.round(gpu.power_limit_w)}W` : ""}`
          : null,
      ]
        .filter(Boolean)
        .join(" · ")
    : "ComfyUI 연결 대기 중";

  return (
    <section
      className={`resource-bar ${queueCount > 0 ? "is-busy" : ""}`}
      aria-label="GPU 및 메모리 사용량"
    >
      <div className="resource-gpu-name">
        <CpuIcon size={15} />
        <div>
          <strong>{gpu ? gpu.name.replace("NVIDIA GeForce ", "") : "GPU 확인 중"}</strong>
          <span>{queueCount > 0 ? `작업 ${queueCount}개 진행/대기 중` : connected ? "대기 중" : "연결 안 됨"}</span>
        </div>
      </div>

      {gpu ? (
        <>
          <Meter
            label="GPU"
            value={`${Math.round(gpuPercent)}%`}
            percent={gpuPercent}
            detail={gpuDetail}
            tone={toneFor(gpuPercent)}
          />
          <Meter
            label="VRAM"
            value={`${Math.round(vramPercent)}%`}
            percent={vramPercent}
            detail={`${formatVram(gpu.vram_used)} / ${formatVram(gpu.vram_total)}`}
            tone={toneFor(vramPercent)}
          />
        </>
      ) : (
        <div className="resource-placeholder">nvidia-smi 정보를 가져오는 중...</div>
      )}

      {memory ? (
        <Meter
          label="RAM"
          value={`${Math.round(ramPercent)}%`}
          percent={ramPercent}
          detail={`${formatVram(memory.used)} / ${formatVram(memory.total)}`}
          tone={toneFor(ramPercent)}
        />
      ) : (
        <div className="resource-placeholder">메모리 정보 없음</div>
      )}

      <div className="resource-queue" title="현재 실행 중 / 대기 중인 작업 수">
        <span className="resource-label">QUEUE</span>
        <strong>
          {queue?.active ?? 0}
          <small> / {queue?.pending ?? 0}</small>
        </strong>
      </div>
    </section>
  );
}
