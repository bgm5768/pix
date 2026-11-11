import type { PageKind, TranslationPreview } from "../types";
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
  autoTranslate: boolean;
  onAutoTranslateChange: (value: boolean) => void;
  translation: TranslationPreview | null;
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
  autoTranslate,
  onAutoTranslateChange,
  translation,
}: PromptPanelProps) {
  const isImage = kind === "image";
  const isReference = kind === "reference";
  const isNative = isImage || isReference;
  return (
    <section className="panel prompt-panel">
      <div className="panel-head">
        <div>
          <span className="eyebrow">{isReference ? "02 · PROMPT" : "01 · PROMPT"}</span>
          <h2>
            {isReference
              ? "참고 이미지를 어떻게 새로 만들까요?"
              : isImage
                ? "어떤 이미지를 만들까요?"
                : "무엇을 만들까요?"}
          </h2>
        </div>
        <span className="micro-badge">
          {isReference ? "IP-ADAPTER · REFERENCE" : isImage ? "SDXL · IMAGE" : "SDXL · LOCAL MODELS"}
        </span>
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
          isReference
            ? "예: 같은 캐릭터가 네온 도시에서 걷는 모습, cinematic lighting, full body"
            : isImage
              ? "예: 숲속을 달리는 호랑이, cinematic lighting, highly detailed, wide shot"
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

      {isNative && (
        <>
          <div className="translate-row">
            <label className="translate-toggle">
              <input
                type="checkbox"
                checked={autoTranslate}
                onChange={(event) => onAutoTranslateChange(event.target.checked)}
              />
              <span>한국어 → 영어 자동 번역</span>
            </label>
            <span className={`translate-badge ${autoTranslate ? "on" : ""}`}>
              {autoTranslate ? "AUTO" : "OFF"}
            </span>
          </div>
          {autoTranslate && translation?.source && (
            <div className={`translation-preview ${translation.status}`}>
              <span className="translation-label">ENGLISH PROMPT</span>
              {translation.status === "loading" ? (
                <p className="translation-loading">
                  <span className="mini-spinner" />
                  영어로 번역하는 중...
                </p>
              ) : translation.status === "error" ? (
                <p className="translation-error">
                  {translation.error ?? "번역하지 못했습니다. 입력한 프롬프트로 생성합니다."}
                </p>
              ) : translation.translated && translation.text ? (
                <p>{translation.text}</p>
              ) : (
                <p className="translation-muted">
                  한국어가 감지되면 자동으로 영어 프롬프트로 바꿔 SDXL에 전달합니다.
                </p>
              )}
            </div>
          )}
        </>
      )}

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
          {isReference
            ? "프롬프트와 참고 이미지가 함께 적용됩니다. 참고 이미지는 외형·화풍·구도를 조건으로 주입하고, 프롬프트가 새 장면과 세부 묘사를 결정합니다."
            : isImage
              ? autoTranslate
                ? "한국어로 입력하면 ONNX 번역 모델이 영어 프롬프트로 바꿔 SDXL에 전달합니다. 영어 입력은 그대로 사용합니다."
                : "자동 번역이 꺼져 있습니다. SDXL은 영어 프롬프트를 가장 잘 이해합니다."
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
              {isReference ? "레퍼런스 생성" : isImage ? "이미지 생성" : "도트 생성"}
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
