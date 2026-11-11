import { useState } from "react";
import type { GenerateRequest, ResultInfo } from "../types";
import { api, assetUrl } from "../api/client";
import { AlertIcon, CheckIcon, PlayIcon, SparkIcon } from "./Icons";

interface ComicCutsProps {
  buildPayload: (prompt: string) => Promise<GenerateRequest>;
  onFinished?: () => void;
  disabled?: boolean;
}

interface CutState {
  prompt: string;
  status: "waiting" | "running" | "done" | "error";
  message: string;
  result: ResultInfo | null;
}

const SLEEP_MS = 1500;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

export function ComicCuts({ buildPayload, onFinished, disabled = false }: ComicCutsProps) {
  const [text, setText] = useState("");
  const [cuts, setCuts] = useState<CutState[]>([]);
  const [running, setRunning] = useState(false);

  const prompts = text
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0);

  const run = async () => {
    if (running || prompts.length === 0) return;
    setRunning(true);
    const results: CutState[] = prompts.map((prompt) => ({
      prompt,
      status: "waiting" as const,
      message: "대기 중",
      result: null,
    }));
    setCuts(results);

    for (let index = 0; index < prompts.length; index += 1) {
      setCuts((current) =>
        current.map((cut, i) =>
          i === index ? { ...cut, status: "running", message: "그리는 중..." } : cut,
        ),
      );
      try {
        const response = await api.generate(await buildPayload(prompts[index]));
        let job = await api.getJob(response.job_id);
        while (["queued", "preparing", "generating", "postprocessing"].includes(job.status)) {
          await sleep(SLEEP_MS);
          job = await api.getJob(response.job_id);
        }
        setCuts((current) =>
          current.map((cut, i) =>
            i === index
              ? {
                  ...cut,
                  status: job.status === "completed" ? "done" : "error",
                  message:
                    job.status === "completed"
                      ? "완료"
                      : (job.error ?? "실패").slice(0, 80),
                  result: job.result ?? null,
                }
              : cut,
          ),
        );
        if (job.status === "completed") onFinished?.();
      } catch (cause) {
        setCuts((current) =>
          current.map((cut, i) =>
            i === index
              ? {
                  ...cut,
                  status: "error",
                  message:
                    cause instanceof Error ? cause.message.slice(0, 80) : "실패",
                }
              : cut,
          ),
        );
      }
    }
    setRunning(false);
  };

  return (
    <section className="panel comic-cuts">
      <div className="panel-head">
        <div>
          <span className="eyebrow">SERIES</span>
          <h2>연재 컷 일괄 만들기</h2>
        </div>
        <span className="micro-badge">{prompts.length} CUTS</span>
      </div>

      <p className="setting-note">
        한 줄에 한 컷씩 적습니다. 참고 이미지·얼굴 고정은 그대로 유지되므로 같은 캐릭터가
        이어서 나옵니다. 순서대로 한 컷씩 그립니다.
      </p>

      <textarea
        className="prompt-input prompt-input-small"
        rows={5}
        value={text}
        disabled={running || disabled}
        placeholder={
          "예: 1. 화이트 배경에 단독으로 서 있는 모습\n2. 창밖을 바라보는 뒷모습\n3. 컵을 든 손 클로즈업"
        }
        onChange={(event) => setText(event.target.value)}
      />

      <div className="comic-cuts-actions">
        <button
          type="button"
          className="btn btn-primary btn-small"
          onClick={() => void run()}
          disabled={running || prompts.length === 0 || disabled}
        >
          {running ? (
            <>
              <span className="spinner" /> 컷 만드는 중...
            </>
          ) : (
            <>
              <PlayIcon size={14} /> 컷 {prompts.length}개 만들기
            </>
          )}
        </button>
        {cuts.length > 0 && (
          <button
            type="button"
            className="text-button"
            onClick={() => setCuts([])}
            disabled={running}
          >
            결과 지우기
          </button>
        )}
      </div>

      {cuts.length > 0 && (
        <div className="comic-cuts-strip">
          {cuts.map((cut, index) => (
            <figure className={`comic-cut is-${cut.status}`} key={`${cut.prompt}-${index}`}>
              {cut.result?.image_url ? (
                <img src={assetUrl(cut.result.image_url)} alt={cut.prompt} />
              ) : (
                <div className="comic-cut-placeholder">
                  {cut.status === "running" ? (
                    <span className="spinner" />
                  ) : cut.status === "error" ? (
                    <AlertIcon size={16} />
                  ) : (
                    <SparkIcon size={16} />
                  )}
                </div>
              )}
              <figcaption>
                <span className="comic-cut-index">{String(index + 1).padStart(2, "0")}</span>
                <span className="comic-cut-prompt">{cut.prompt}</span>
                <span className="comic-cut-status">
                  {cut.status === "done" ? <CheckIcon size={11} /> : null}
                  {cut.message}
                </span>
              </figcaption>
            </figure>
          ))}
        </div>
      )}
    </section>
  );
}
