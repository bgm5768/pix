import type { JobStatus, JobView } from "../types";
import { formatRelative } from "../utils";
import { AlertIcon, CheckIcon, RefreshIcon, StopIcon } from "./Icons";

interface JobListProps {
  jobs: JobView[];
  loading: boolean;
  activeJobId: string | null;
  onCancel: (jobId: string) => void;
  onSelect: (job: JobView) => void;
  onRefresh: () => void;
}

const ACTIVE_STATUSES: JobStatus[] = [
  "queued",
  "preparing",
  "generating",
  "postprocessing",
];

const STATUS_LABEL: Record<JobStatus, string> = {
  queued: "대기",
  preparing: "준비",
  generating: "생성 중",
  postprocessing: "후처리",
  completed: "완료",
  error: "오류",
  cancelled: "취소",
};

function isActive(status: JobStatus): boolean {
  return ACTIVE_STATUSES.includes(status);
}

function shortModel(name: string | null | undefined): string {
  if (!name) return "기본 모델";
  const base = name.split(/[\\/]/).pop() ?? name;
  return base.replace(/\.safetensors$/i, "");
}

function promptExcerpt(job: JobView): string {
  const text = (job.prompt_original || job.request.prompt || "").trim().replace(/\s+/g, " ");
  if (!text) return "(프롬프트 없음)";
  return text.length > 64 ? `${text.slice(0, 64)}…` : text;
}

export function JobList({
  jobs,
  loading,
  activeJobId,
  onCancel,
  onSelect,
  onRefresh,
}: JobListProps) {
  return (
    <section className="panel job-list-panel" aria-live="polite">
      <div className="panel-head">
        <div>
          <span className="eyebrow">JOBS · HISTORY</span>
          <h2>작업 목록</h2>
        </div>
        <div className="job-list-head-actions">
          <span className="micro-badge">{jobs.length}개</span>
          <button
            type="button"
            className="icon-button"
            onClick={onRefresh}
            title="작업 목록 새로고침"
            aria-label="작업 목록 새로고침"
          >
            <RefreshIcon size={14} />
          </button>
        </div>
      </div>

      {jobs.length === 0 ? (
        <div className="job-list-empty">
          {loading ? "작업 목록을 불러오는 중..." : "아직 작업이 없습니다."}
        </div>
      ) : (
        <div className="job-list">
          {jobs.map((job) => {
            const busy = isActive(job.status);
            const kind = job.request.kind === "image" ? "이미지" : "픽셀";
            const selected = job.job_id === activeJobId;
            return (
              <div
                key={job.job_id}
                className={`job-row status-${job.status} ${selected ? "is-selected" : ""}`}
              >
                <button
                  type="button"
                  className="job-row-main"
                  onClick={() => onSelect(job)}
                  disabled={busy || job.status !== "completed" || !job.result}
                  title={
                    job.status === "completed" && job.result
                      ? "결과 보기"
                      : job.stage_message
                  }
                >
                  <span className={`job-status status-${job.status}`}>
                    {job.status === "completed" ? (
                      <CheckIcon size={11} />
                    ) : job.status === "error" ? (
                      <AlertIcon size={11} />
                    ) : busy ? (
                      <span className="job-pulse" />
                    ) : null}
                    {STATUS_LABEL[job.status]}
                  </span>
                  <span className="job-copy">
                    <strong>{promptExcerpt(job)}</strong>
                    <small>
                      {kind} · {shortModel(job.request.checkpoint)} · {formatRelative(job.created_at)}
                    </small>
                  </span>
                  {busy && (
                    <span className="job-progress">
                      <span style={{ width: `${Math.max(2, Math.min(100, job.progress))}%` }} />
                    </span>
                  )}
                </button>
                {busy ? (
                  <button
                    type="button"
                    className="job-cancel"
                    onClick={() => onCancel(job.job_id)}
                    title="이 작업 취소"
                    aria-label={`${STATUS_LABEL[job.status]} 작업 취소`}
                  >
                    <StopIcon size={13} />
                  </button>
                ) : (
                  <span className="job-percent">
                    {job.status === "completed" ? `${job.progress}%` : job.stage_message}
                  </span>
                )}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
