import type { PageKind } from "../types";
import { InfoIcon, SparkIcon, StopIcon } from "./Icons";

interface PromptPanelProps {
  kind: PageKind;
  prompt: string;
  negativePrompt: string;
  onPromptChange: (value: string) => void;
  onNegativeChange: (value: string) => void;
  onResetNegative: () => void;
  onGenerate: () => void;
  onCancel: () => void;
  busy: boolean;
  canGenerate: boolean;
}

export function PromptPanel({
  kind,
  prompt,
  negativePrompt,
  onPromptChange,
  onNegativeChange,
  onResetNegative,
  onGenerate,
  onCancel,
  busy,
  canGenerate,
}: PromptPanelProps) {
  const isImage = kind === "image";
  return (
    <section className="panel prompt-panel">
      <div className="panel-head">
        <div>
          <span className="eyebrow">01 · PROMPT</span>
          <h2>{isImage ? "어떤 이미지를 만들까요?" : "무엇을 만들까요?"}</h2>
        </div>
        <span className="micro-badge">{isImage ? "SDXL · IMAGE" : "SDXL · LOCAL MODELS"}</span>
      </div>

      <label className="field-label" htmlFor="positive-prompt">
        POSITIVE PROMPT
      </label>
      <textarea
        id="positive-prompt"
        className="prompt-input"
        rows={5}
        maxLength={2000}
        value={prompt}
        placeholder={
          isImage
            ? "예: a lone lighthouse on a rocky cliff at sunset, cinematic lighting, highly detailed, wide shot"
            : "예: a tiny knight standing and holding a glowing sword, full body, feet visible, side view, game sprite, fantasy"
        }
        onChange={(event) => onPromptChange(event.target.value)}
        onKeyDown={(event) => {
          if ((event.ctrlKey || event.metaKey) && event.key === "Enter" && canGenerate && !busy) {
            event.preventDefault();
            onGenerate();
          }
        }}
      />
      <div className="field-foot">
        <span>{prompt.length} / 2000</span>
        <span>Ctrl + Enter로 생성</span>
      </div>

      <div className="field-label-row">
        <label className="field-label" htmlFor="negative-prompt">
          NEGATIVE PROMPT
        </label>
        <button type="button" className="text-button" onClick={onResetNegative}>
          기본값 복원
        </button>
      </div>
      <textarea
        id="negative-prompt"
        className="prompt-input prompt-input-small"
        rows={3}
        maxLength={2000}
        value={negativePrompt}
        onChange={(event) => onNegativeChange(event.target.value)}
      />

      <div className="prompt-hint">
        <InfoIcon size={15} />
        <span>
          {isImage
            ? "SDXL 원본 이미지를 그대로 저장합니다. 픽셀 팔레트·후처리·자동 검증은 적용되지 않습니다."
            : "픽셀 경계·제한 팔레트·실루엣을 위한 스타일 프롬프트가 자동으로 추가됩니다. 네거티브는 직접 수정할 수 있습니다."}
        </span>
      </div>

      <div className="prompt-actions">
        <button
          type="button"
          className="btn btn-primary btn-generate"
          disabled={!canGenerate || busy}
          onClick={onGenerate}
        >
          {busy ? (
            <>
              <span className="spinner" />
              생성 중...
            </>
          ) : (
            <>
              <SparkIcon size={18} />
              {isImage ? "이미지 생성" : "도트 생성"}
            </>
          )}
        </button>
        {busy && (
          <button type="button" className="btn btn-ghost btn-cancel" onClick={onCancel}>
            <StopIcon size={16} />
            취소
          </button>
        )}
      </div>
    </section>
  );
}
