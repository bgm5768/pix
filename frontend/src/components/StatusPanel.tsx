import type { JobView, PageKind } from "../types";
import { formatDuration } from "../utils";
import { AlertIcon, CheckIcon, ClockIcon, RefreshIcon, StopIcon } from "./Icons";

interface StatusPanelProps {
  kind: PageKind;
  job: JobView | null;
  jobId: string | null;
  error: string | null;
  notice: string | null;
  onRetry: () => void;
  onCancel: () => void;
}

const STAGES = [
  { key: "preparing", label: "프롬프트 처리" },
  { key: "generating", label: "모델 생성" },
  { key: "postprocessing", label: "후처리" },
  { key: "completed", label: "완료" },
] as const;

const STAGE_INDEX: Record<string, number> = {
  queued: -1,
  preparing: 0,
  generating: 1,
  postprocessing: 2,
  completed: 3,
  error: -1,
  cancelled: -1,
};

export function StatusPanel({
  kind,
  job,
  jobId,
  error,
  notice,
  onRetry,
  onCancel,
}: StatusPanelProps) {
  const isImage = kind === "image";
  const active = Boolean(jobId);
  const status = job?.status ?? (active ? "queued" : "idle");
  const currentIndex = STAGE_INDEX[status] ?? -1;
  const progress = job?.progress ?? (active ? 2 : 0);
  const isBusy = active && !["completed", "error", "cancelled"].includes(status);
  const errorMessage = error ?? job?.error ?? null;
  const duration = job ? formatDuration(job.started_at, job.completed_at) : "—";

  let headline = "대기 중";
  if (active && !job) headline = "작업을 준비하는 중...";
  if (job) headline = job.stage_message;
  if (status === "completed") headline = "완료";
  if (status === "error") headline = "오류 발생";
  if (status === "cancelled") headline = "취소됨";

  return (
    <section className="panel status-panel" aria-live="polite">
      <div className="status-head">
        <div className="status-head-copy">
          <span className="eyebrow">03 · PROGRESS</span>
          <h2>{headline}</h2>
        </div>
        <div className={`run-state run-${status}`}>
          <span className="run-dot" />
          {status === "idle"
            ? "IDLE"
            : status === "completed"
              ? "DONE"
              : status === "error"
                ? "ERROR"
                : status === "cancelled"
                  ? "CANCELLED"
                  : "RUNNING"}
        </div>
      </div>

      {status === "idle" ? (
        <div className="status-idle">
          <div className="idle-pulse" />
          <div>
            <strong>GPU 대기 중</strong>
            <p>
              프롬프트를 입력하고 {isImage ? "이미지 생성" : "도트 생성"}을 누르면 로컬
              ComfyUI에서 {isImage ? "SDXL 이미지를" : "도트를"} 만듭니다.
            </p>
          </div>
        </div>
      ) : (
        <>
          <div className="progress-track">
            <div
              className={`progress-fill ${isBusy ? "is-running" : ""}`}
              style={{ width: `${Math.max(2, Math.min(100, progress))}%` }}
            />
          </div>
          <div className="progress-meta">
            <span>{Math.max(0, Math.min(100, Math.round(progress)))}%</span>
            <span className="progress-detail">
              {job?.status === "queued" && job.queue_position > 0
                ? `대기열 ${job.queue_position}번째`
                : job && job.total_steps > 0
                  ? `${job.step} / ${job.total_steps} steps`
                  : active
                    ? "ComfyUI 준비 중"
                    : "—"}
            </span>
            <span className="progress-detail">
              <ClockIcon size={13} /> {duration}
            </span>
          </div>

          <div className="stage-list">
            {STAGES.map((stage, index) => {
              const done = currentIndex > index || status === "completed";
              const current = currentIndex === index && status !== "completed";
              return (
                <div key={stage.key} className={`stage ${done ? "done" : ""} ${current ? "active" : ""}`}>
                  <span className="stage-dot">{done ? <CheckIcon size={11} /> : index + 1}</span>
                  <span>{stage.label}</span>
                </div>
              );
            })}
          </div>

          {isBusy && (
            <div className="status-actions">
              <button type="button" className="text-button danger" onClick={onCancel}>
                <StopIcon size={14} />
                생성 취소
              </button>
            </div>
          )}
        </>
      )}

      {notice && <div className="notice-box">{notice}</div>}

      {errorMessage && (
        <div className="error-box">
          <AlertIcon size={18} />
          <div className="error-copy">
            <strong>생성에 실패했습니다</strong>
            <p>{errorMessage}</p>
            {job?.error_code && <code>{job.error_code}</code>}
          </div>
          <button type="button" className="btn btn-small btn-ghost" onClick={onRetry}>
            <RefreshIcon size={14} />
            다시 시도
          </button>
        </div>
      )}

      {status === "completed" && !errorMessage && (
        <div className="success-box">
          <CheckIcon size={16} />
          <span>
            생성 완료. {isImage ? "원본 이미지를 PNG로" : "결과를 PNG로"} 저장하거나 다시
            생성해 보세요.
          </span>
        </div>
      )}
    </section>
  );
}
