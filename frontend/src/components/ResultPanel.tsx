import type {
  AssetMode,
  DisplayResult,
  PageKind,
  PostProcessMode,
  ResizeFilter,
} from "../types";
import { assetUrl } from "../api/client";
import { DownloadIcon, PaletteIcon, RefreshIcon, SparkIcon, TrashIcon } from "./Icons";

interface ResultPanelProps {
  kind: PageKind;
  display: DisplayResult | null;
  busy: boolean;
  onRegenerate: () => void;
  onDelete: () => void;
}

const POSTPROCESS_LABELS: Record<PostProcessMode, string> = {
  quantize: "퀀타이즈",
  nearest: "니어리스트",
  posterize: "포스터라이즈",
};

const MODE_LABELS: Record<AssetMode, string> = {
  icon: "아이콘",
  character: "캐릭터",
  object: "오브젝트",
  tile: "타일",
};

const RESIZE_LABELS: Record<ResizeFilter, string> = {
  nearest: "NN",
  box: "BOX",
  lanczos: "LANCZOS",
};

const EMPTY_PIXELS = [
  "00111100",
  "01111110",
  "11011011",
  "11111111",
  "01111110",
  "00111100",
  "01100110",
  "11000011",
];

export function ResultPanel({ kind, display, busy, onRegenerate, onDelete }: ResultPanelProps) {
  const isImage = kind === "image";
  const result = display?.result ?? null;
  const scale = result?.preview_scale ?? 1;
  const imageSrc = result?.image_url ?? result?.preview_url;
  const pixelSrc = result?.pixel_url ?? result?.preview_url;

  return (
    <section className="panel result-panel">
      <div className="panel-head">
        <div>
          <span className="eyebrow">04 · RESULT</span>
          <h2>{isImage ? "이미지 결과" : "도트 결과"}</h2>
        </div>
        <div className="result-head-badges">
          {!isImage && result?.transparent && (
            <span className="micro-badge magenta">TRANSPARENT</span>
          )}
          {isImage && result && <span className="micro-badge cyan">SDXL NATIVE</span>}
          <span className="micro-badge">
            {result ? `${result.width}×${result.height} PX` : "NO OUTPUT"}
          </span>
        </div>
      </div>

      {!result || !display ? (
        <div className="result-empty">
          <div className="empty-art" aria-hidden="true">
            {EMPTY_PIXELS.flatMap((row, y) =>
              row.split("").map((cell, x) => (
                <span key={`${y}-${x}`} className={cell === "1" ? "on" : ""} />
              )),
            )}
          </div>
          <h3>{isImage ? "아직 생성된 이미지가 없습니다" : "아직 생성된 도트가 없습니다"}</h3>
          <p>
            왼쪽에 프롬프트를 입력하고 <strong>{isImage ? "이미지 생성" : "도트 생성"}</strong>을
            눌러 보세요.
            <br />
            {isImage
              ? "SDXL이 만든 원본 이미지를 PNG로 저장합니다."
              : "생성된 결과는 실제 픽셀 크기 그대로 PNG로 저장됩니다."}
          </p>
        </div>
      ) : (
        <>
          <div className={`preview-stage ${isImage ? "image-stage" : "checker"}`}>
            <img
              className={`preview-image ${isImage ? "image-preview" : ""}`}
              src={assetUrl(isImage ? imageSrc : pixelSrc)}
              alt={
                isImage
                  ? `${result.width}×${result.height} 생성 이미지`
                  : `${result.width}×${result.height} 픽셀아트 결과`
              }
              style={isImage ? undefined : { imageRendering: "pixelated" }}
            />
            <span className="preview-tag top-left">
              {isImage ? "SDXL · NATIVE" : `×${scale} NEAREST`}
            </span>
            <span className="preview-tag bottom-right">
              {result.width} × {result.height} px
            </span>
            {busy && (
              <div className="preview-busy">
                <span className="spinner" />
                {isImage ? "새 이미지를 만드는 중..." : "새 도트를 만드는 중..."}
              </div>
            )}
          </div>

          {!isImage && (
            <div className="compare-grid compare-grid-4">
              <figure>
                <div className="compare-frame checker">
                  <img src={assetUrl(result.original_url)} alt="AI 원본 이미지" />
                </div>
                <figcaption>
                  AI 원본 <b>512×512</b>
                </figcaption>
              </figure>
              {result.cutout_url && (
                <figure>
                  <div className="compare-frame checker">
                    <img src={assetUrl(result.cutout_url)} alt="배경 제거 결과" />
                  </div>
                  <figcaption>배경 제거</figcaption>
                </figure>
              )}
              {result.crop_url && (
                <figure>
                  <div className="compare-frame checker">
                    <img src={assetUrl(result.crop_url)} alt="피사체 자동 크롭 결과" />
                  </div>
                  <figcaption>자동 크롭</figcaption>
                </figure>
              )}
              <figure>
                <div className="compare-frame checker">
                  <img
                    src={assetUrl(pixelSrc)}
                    alt={`최종 ${result.width}×${result.height} 도트 이미지`}
                    style={{ imageRendering: "pixelated" }}
                  />
                </div>
                <figcaption>
                  최종 도트{" "}
                  <b>
                    {result.width}×{result.height}
                  </b>
                </figcaption>
              </figure>
            </div>
          )}

          <div className="result-meta">
            <span className="meta-chip">
              <SparkIcon size={13} /> Seed {display.seed ?? "—"}
            </span>
            {isImage ? (
              <>
                <span className="meta-chip">
                  <PaletteIcon size={13} />
                  {result.width}×{result.height} 원본 PNG
                </span>
                <span className="meta-chip">픽셀 후처리 없음</span>
              </>
            ) : (
              <>
                <span className="meta-chip">
                  <PaletteIcon size={13} />
                  {result.palette_colors > 0
                    ? `${result.palette_colors} colors`
                    : "raw colors"}
                </span>
                <span className="meta-chip">
                  {result.transparent ? "투명 PNG" : "불투명 PNG"}
                </span>
                <span className="meta-chip">{POSTPROCESS_LABELS[result.postprocess]}</span>
                <span className="meta-chip">{MODE_LABELS[result.mode]}</span>
                <span className="meta-chip">{RESIZE_LABELS[result.resize_filter]}</span>
                {result.subject_fill > 0 && (
                  <span className="meta-chip">
                    채움 {Math.round(result.subject_fill * 100)}%
                  </span>
                )}
              </>
            )}
            {result.candidates_generated > 1 && (
              <span className="meta-chip">
                후보 {result.candidates_generated}개 중 #{result.candidate_index + 1}
              </span>
            )}
          </div>

          {display.prompt && (
            <p className="result-prompt" title={display.prompt}>
              {display.prompt}
            </p>
          )}

          {!isImage && display.promptPlan && (
            <details className="plan-details">
              <summary>
                프롬프트 구조 · {display.promptPlan.source === "llm" ? "로컬 LLM" : "템플릿"}
              </summary>
              <dl>
                <div>
                  <dt>피사체</dt>
                  <dd>{display.promptPlan.subject}</dd>
                </div>
                <div>
                  <dt>구도</dt>
                  <dd>{display.promptPlan.composition}</dd>
                </div>
                <div>
                  <dt>시점</dt>
                  <dd>{display.promptPlan.view}</dd>
                </div>
                <div>
                  <dt>배경</dt>
                  <dd>{display.promptPlan.background}</dd>
                </div>
              </dl>
              <p className="plan-positive">{display.promptPlan.positive}</p>
            </details>
          )}

          {!isImage && result.quality.length > 0 && (
            <div className="quality-panel">
              <div className="quality-head">
                <strong>자동 검증</strong>
                <span>
                  {result.quality.filter((check) => check.passed).length}/{result.quality.length} 통과
                </span>
              </div>
              <ul className="quality-list">
                {result.quality.map((check) => (
                  <li key={check.key} className={check.passed ? "pass" : "fail"}>
                    <span className="quality-mark">{check.passed ? "✓" : "!"}</span>
                    <span className="quality-label">{check.label}</span>
                    <span className="quality-value">{check.value}</span>
                  </li>
                ))}
              </ul>
              <p className="quality-note">
                실패 항목이 있어도 결과는 자동 삭제되지 않습니다. 미리보기를 확인해 주세요.
              </p>
            </div>
          )}

          {result.warnings.length > 0 && (
            <div className="warning-list">
              {result.warnings.map((warning) => (
                <p key={warning}>{warning}</p>
              ))}
            </div>
          )}

          <div className="result-actions">
            <a
              className="btn btn-primary"
              href={assetUrl(result.download_url)}
              download={
                isImage
                  ? `pixelforge_${display.jobId}_image_${result.width}px.png`
                  : `pixelforge_${display.jobId}_${result.width}px.png`
              }
            >
              <DownloadIcon size={17} />
              PNG 저장
            </a>
            <button
              type="button"
              className="btn btn-ghost"
              onClick={onRegenerate}
              disabled={busy}
            >
              <RefreshIcon size={16} />
              다시 생성
            </button>
            <button
              type="button"
              className="btn btn-ghost btn-delete"
              onClick={onDelete}
              disabled={busy}
            >
              <TrashIcon size={16} />
              삭제
            </button>
            <a
              className="text-button result-original-link"
              href={assetUrl(result.original_url)}
              target="_blank"
              rel="noreferrer"
            >
              원본 열기
            </a>
          </div>
        </>
      )}
    </section>
  );
}
