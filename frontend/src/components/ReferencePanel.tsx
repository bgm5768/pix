import { useRef, useState } from "react";
import type {
  IdentityEngine,
  IdentityMethod,
  ReferenceAsset,
  ReferenceCapabilities,
  ReferenceFocus,
  ReferenceItem,
} from "../types";
import { assetUrl } from "../api/client";
import {
  AlertIcon,
  CheckIcon,
  ImageIcon,
  InfoIcon,
  RefreshIcon,
  SparkIcon,
  TrashIcon,
  UploadIcon,
} from "./Icons";

const FOCUS_OPTIONS: Array<{
  value: ReferenceFocus;
  label: string;
  hint: string;
}> = [
  {
    value: "appearance",
    label: "외형 · 캐릭터",
    hint: "인물·동물의 생김새, 색감, 질감을 가져옵니다.",
  },
  {
    value: "face",
    label: "얼굴 · 표정",
    hint: "Plus Face 모델로 얼굴 특징을 더 강하게 반영합니다.",
  },
  {
    value: "style",
    label: "화풍 · 그림체",
    hint: "스타일 전이 레이어만 참고해 새 이미지의 화풍을 바꿉니다.",
  },
  {
    value: "pose",
    label: "포즈 · 자세",
    hint: "구도 레이어를 참고합니다. 정확한 관절 포즈는 ControlNet OpenPose가 더 적합합니다.",
  },
  {
    value: "composition",
    label: "구도 · 배치",
    hint: "카메라 구도와 화면 안 피사체 배치를 참고합니다.",
  },
];

const IDENTITY_ENGINES: Array<{
  value: IdentityEngine;
  label: string;
  hint: string;
}> = [
  {
    value: "none",
    label: "사용 안 함",
    hint: "IP-Adapter만으로 참고 이미지의 외형·화풍을 반영합니다.",
  },
  {
    value: "instantid",
    label: "InstantID",
    hint: "얼굴 임베딩 + SDXL ControlNet으로 얼굴을 강하게 고정합니다. 단일 인물 초상에 적합합니다.",
  },
  {
    value: "pulid",
    label: "PuLID",
    hint: "ID 임베딩을 UNet에 직접 주입해 정체성을 유지합니다. EVA-CLIP이 추가로 필요합니다.",
  },
];

const IDENTITY_METHODS: Array<{ value: IdentityMethod; label: string }> = [
  { value: "fidelity", label: "fidelity · 참조에 충실" },
  { value: "style", label: "style · 자유도 유지" },
  { value: "neutral", label: "neutral · 정규화 없음" },
];

interface ReferencePanelProps {
  items: ReferenceItem[];
  samples: ReferenceAsset[];
  capabilities: ReferenceCapabilities | null;
  samplesLoading: boolean;
  capabilitiesLoading: boolean;
  capabilitiesError: string | null;
  checkpoint: string | null;
  maxReferences: number;
  busy: boolean;
  uploading: boolean;
  uploadError: string | null;
  identityEngine: IdentityEngine;
  identityMethod: IdentityMethod;
  identityWeight: number;
  identityImage: string | null;
  onAddAsset: (asset: ReferenceAsset) => void;
  onUploadFile: (file: File, replaceAssetId?: string) => void;
  onUpdateItem: (
    assetId: string,
    patch: Partial<Pick<ReferenceItem, "focus" | "strength">>,
  ) => void;
  onRemoveItem: (assetId: string) => void;
  onRefreshSamples: () => void;
  onRefreshCapabilities: () => void;
  onIdentityChange: (
    patch: Partial<{
      engine: IdentityEngine;
      method: IdentityMethod;
      weight: number;
      image: string | null;
    }>,
  ) => void;
}

function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${bytes} B`;
}

export function ReferencePanel({
  items,
  samples,
  capabilities,
  samplesLoading,
  capabilitiesLoading,
  capabilitiesError,
  checkpoint,
  maxReferences,
  busy,
  uploading,
  uploadError,
  identityEngine,
  identityMethod,
  identityWeight,
  identityImage,
  onAddAsset,
  onUploadFile,
  onUpdateItem,
  onRemoveItem,
  onRefreshSamples,
  onRefreshCapabilities,
  onIdentityChange,
}: ReferencePanelProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const replaceTargetRef = useRef<string | undefined>(undefined);
  const [dragging, setDragging] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(true);
  const selectedIds = new Set(items.map((item) => item.id));
  const atLimit = items.length >= maxReferences;
  const faceWithoutModel = Boolean(
    capabilities && !capabilities.plus_face_model && items.some((item) => item.focus === "face"),
  );
  const ready =
    Boolean(capabilities?.available) && capabilities?.checkpoint_compatible !== false;
  const engineReady = (engine: IdentityEngine) => {
    if (engine === "none") return true;
    if (!capabilities) return false;
    return capabilities.identity_engines.includes(engine);
  };
  const identitySource = items.find((item) => item.id === identityImage) ?? null;

  const openPicker = (replaceAssetId?: string) => {
    replaceTargetRef.current = replaceAssetId;
    inputRef.current?.click();
  };

  const handleFiles = (fileList: FileList | null) => {
    const file = fileList?.[0];
    if (!file) return;
    onUploadFile(file, replaceTargetRef.current);
    replaceTargetRef.current = undefined;
  };

  return (
    <section className="panel reference-panel">
      <div className="panel-head">
        <div>
          <span className="eyebrow">01 · REFERENCES</span>
          <h2>참고 이미지</h2>
        </div>
        <span className="micro-badge">
          {items.length}/{maxReferences} 선택
        </span>
      </div>

      <div className={`reference-status ${ready ? "ok" : capabilities ? "bad" : "neutral"}`}>
        <div className="reference-status-head">
          <span className="reference-status-icon">
            {capabilitiesLoading ? (
              <SparkIcon size={15} />
            ) : ready ? (
              <CheckIcon size={15} />
            ) : (
              <AlertIcon size={15} />
            )}
          </span>
          <div>
            <strong>
              {capabilitiesLoading
                ? "IP-Adapter 상태 확인 중..."
                : ready
                  ? "IP-Adapter Plus 사용 가능"
                  : capabilities
                    ? "IP-Adapter Plus를 사용할 수 없습니다"
                    : "IP-Adapter 상태를 확인하지 못했습니다"}
            </strong>
            <span>
              {capabilities?.checkpoint_note ||
                (capabilitiesError
                  ? capabilitiesError
                  : "SDXL 계열 체크포인트에서 참고 이미지의 외형·화풍·구도를 반영합니다.")}
            </span>
          </div>
          <button
            type="button"
            className="icon-button reference-refresh"
            onClick={onRefreshCapabilities}
            title="IP-Adapter 상태 새로고침"
          >
            <RefreshIcon size={14} />
          </button>
        </div>
        {capabilities && (
          <div className="reference-model-state">
            <span className={capabilities.node_installed ? "ok" : "bad"}>
              NODE {capabilities.node_installed ? "OK" : "MISSING"}
            </span>
            <span className={capabilities.plus_model ? "ok" : "bad"}>
              PLUS {capabilities.plus_model ? "OK" : "MISSING"}
            </span>
            <span className={capabilities.plus_face_model ? "ok" : "neutral"}>
              FACE {capabilities.plus_face_model ? "OK" : "OPTIONAL"}
            </span>
            <span className={capabilities.clip_vision_model ? "ok" : "bad"}>
              CLIP-VISION {capabilities.clip_vision_model ? "OK" : "MISSING"}
            </span>
            <span className={capabilities.checkpoint_compatible === false ? "bad" : "ok"}>
              SDXL {capabilities.checkpoint_compatible === false ? "CHECK" : "OK"}
            </span>
          </div>
        )}
        {capabilities && !ready && (capabilities.guidance || capabilities.checkpoint_note) && (
          <p className="reference-guidance">
            {capabilities.guidance || capabilities.checkpoint_note}
          </p>
        )}
        {capabilities && !ready && capabilities.install_hint && (
          <p className="reference-guidance is-muted">{capabilities.install_hint}</p>
        )}
        {faceWithoutModel && (
          <p className="reference-guidance is-warning">
            Plus Face 모델이 없어 얼굴 참고를 일반 Plus 모델로 적용합니다.
          </p>
        )}
      </div>

      <div className="reference-add">
        <div className="reference-add-head">
          <span className="field-label">ADD REFERENCE</span>
          <span className="reference-limit">
            최대 {maxReferences}장 · {checkpoint || "체크포인트 미선택"}
          </span>
        </div>
        <div
          className={`reference-dropzone ${dragging ? "is-dragging" : ""} ${
            atLimit ? "is-disabled" : ""
          }`}
          onDragOver={(event) => {
            event.preventDefault();
            if (!atLimit) setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            if (atLimit || busy || uploading) return;
            handleFiles(event.dataTransfer.files);
          }}
          onClick={() => {
            if (!atLimit && !busy && !uploading) openPicker();
          }}
          role="button"
          tabIndex={0}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              if (!atLimit && !busy && !uploading) openPicker();
            }
          }}
        >
          <UploadIcon size={20} />
          <div>
            <strong>
              {uploading
                ? "이미지를 업로드하는 중..."
                : atLimit
                  ? "최대 장수에 도달했습니다"
                  : "클릭하거나 이미지를 끌어다 놓으세요"}
            </strong>
            <span>사람 · 동물 · 캐릭터 · 그림 · 장면 모두 사용할 수 있습니다 (최대 15MB)</span>
          </div>
        </div>
        <input
          ref={inputRef}
          className="reference-file-input"
          type="file"
          accept="image/png,image/jpeg,image/webp,image/bmp,image/gif,image/tiff"
          onChange={(event) => {
            handleFiles(event.target.files);
            event.target.value = "";
          }}
        />
        {uploadError && <p className="reference-guidance is-warning">{uploadError}</p>}

        <div className="reference-sample-head">
          <button
            type="button"
            className="reference-section-toggle"
            onClick={() => setPickerOpen((open) => !open)}
            aria-expanded={pickerOpen}
          >
            <ImageIcon size={14} />
            샘플 이미지에서 선택
          </button>
          <button
            type="button"
            className="icon-button"
            onClick={onRefreshSamples}
            title="샘플 목록 새로고침"
          >
            <RefreshIcon size={13} />
          </button>
        </div>

        {pickerOpen && (
          <div className="reference-samples">
            {samplesLoading && samples.length === 0 && (
              <div className="reference-samples-empty">샘플을 불러오는 중...</div>
            )}
            {!samplesLoading && samples.length === 0 && (
              <div className="reference-samples-empty">
                샘플 이미지가 없습니다. 직접 업로드해서 사용해 주세요.
              </div>
            )}
            {samples.map((sample) => {
              const selected = selectedIds.has(sample.id);
              return (
                <button
                  key={sample.id}
                  type="button"
                  className={`reference-sample ${selected ? "is-selected" : ""}`}
                  onClick={() => {
                    if (selected) {
                      onRemoveItem(sample.id);
                    } else if (!atLimit) {
                      onAddAsset(sample);
                    }
                  }}
                  disabled={busy || uploading || (atLimit && !selected)}
                  title={
                    selected
                      ? "클릭해서 선택 해제"
                      : atLimit
                        ? "최대 장수에 도달했습니다"
                        : sample.hint || sample.name
                  }
                >
                  <img src={assetUrl(sample.url)} alt={sample.name} loading="lazy" />
                  <span className="reference-sample-overlay">
                    <strong>{sample.name}</strong>
                    <small>{sample.hint || sample.analysis.subject_hint}</small>
                  </span>
                  {selected && (
                    <span className="reference-sample-check">
                      <CheckIcon size={12} />
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        )}
      </div>

      <div className="reference-identity">
        <div className="reference-identity-head">
          <span className="field-label">얼굴 동일성 고정 · FACE IDENTITY</span>
          <span className="micro-badge">
            {identityEngine === "none"
              ? "OFF"
              : identityEngine === "instantid"
                ? "INSTANTID"
                : "PULID"}
          </span>
        </div>

        <div className="identity-switch">
          {IDENTITY_ENGINES.map((engine) => {
            const available = engineReady(engine.value);
            const active = identityEngine === engine.value;
            return (
              <button
                key={engine.value}
                type="button"
                className={`identity-option ${active ? "is-active" : ""} ${
                  available ? "" : "is-missing"
                }`}
                onClick={() => onIdentityChange({ engine: engine.value })}
                disabled={busy}
                title={
                  available
                    ? engine.hint
                    : `${engine.label} 설치가 필요합니다. ${capabilities?.identity_guidance ?? ""}`
                }
              >
                <strong>{engine.label}</strong>
                <small>
                  {engine.value === "none"
                    ? "IP-Adapter만 사용"
                    : available
                      ? "설치 완료"
                      : "설치 필요"}
                </small>
              </button>
            );
          })}
        </div>

        {identityEngine !== "none" && (
          <>
            <p className="reference-focus-hint">
              {IDENTITY_ENGINES.find((engine) => engine.value === identityEngine)?.hint}
            </p>
            <div className="reference-identity-grid">
              <label className="reference-control">
                <span>얼굴 고정용 이미지</span>
                <select
                  className="select-input select-small"
                  value={identityImage ?? ""}
                  onChange={(event) =>
                    onIdentityChange({ image: event.target.value || null })
                  }
                  disabled={busy || items.length === 0}
                >
                  <option value="">선택해 주세요</option>
                  {items.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
                </select>
              </label>
              {identityEngine === "pulid" && (
                <label className="reference-control">
                  <span>적용 방식</span>
                  <select
                    className="select-input select-small"
                    value={identityMethod}
                    onChange={(event) =>
                      onIdentityChange({ method: event.target.value as IdentityMethod })
                    }
                    disabled={busy}
                  >
                    {IDENTITY_METHODS.map((method) => (
                      <option key={method.value} value={method.value}>
                        {method.label}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              <label className="reference-control reference-strength">
                <span>
                  IDENTITY <strong>×{identityWeight.toFixed(2)}</strong>
                </span>
                <input
                  type="range"
                  min={0}
                  max={2}
                  step={0.05}
                  value={identityWeight}
                  onChange={(event) =>
                    onIdentityChange({ weight: Number(event.target.value) })
                  }
                  disabled={busy}
                />
              </label>
            </div>
            {!identityImage && (
              <p className="reference-guidance is-warning">
                얼굴을 고정할 참고 이미지를 선택해 주세요. 얼굴이 정면으로 보이는 사진이 가장
                잘됩니다.
              </p>
            )}
            {identitySource && identitySource.focus !== "face" && (
              <p className="reference-guidance">
                선택한 참고 이미지의 초점이 &quot;{identitySource.focus}&quot;입니다. 얼굴 고정
                전용으로 쓸 거라면 초점을 &quot;얼굴 · 표정&quot;으로 바꾸는 편이 자연스럽습니다.
              </p>
            )}
            {identityEngine === "instantid" && (
              <p className="reference-guidance is-muted">
                InstantID는 CFG를 4~5로 낮추면 얼굴이 더 자연스럽게 유지됩니다. 워터마크를
                피하려면 1024px 대신 1016px 해상도를 권장합니다.
              </p>
            )}
            {identityEngine === "pulid" && (
              <p className="reference-guidance is-muted">
                PuLID는 EVA-CLIP을 추가로 사용하므로 VRAM을 더 많이 먹고, 기준 체크포인트
                품질에 따라 결과 편차가 있습니다.
              </p>
            )}
            {!engineReady(identityEngine) && capabilities?.identity_guidance && (
              <p className="reference-guidance is-warning">
                {capabilities.identity_guidance}
              </p>
            )}
          </>
        )}
      </div>

      {items.length > 0 && (
        <div className="reference-list">
          {items.map((item, index) => (
            <article className="reference-card" key={item.id}>
              <div className="reference-thumb">
                <img src={assetUrl(item.url)} alt={item.name} />
                <span className="reference-order">{String(index + 1).padStart(2, "0")}</span>
              </div>
              <div className="reference-card-body">
                <div className="reference-card-head">
                  <div>
                    <strong title={item.name}>{item.name}</strong>
                    <span className="reference-meta">
                      {item.width}×{item.height} · {formatBytes(item.size_bytes)} ·{" "}
                      {item.source === "sample" ? "샘플" : "업로드"}
                    </span>
                  </div>
                  <div className="reference-card-actions">
                    <button
                      type="button"
                      className="text-button"
                      onClick={() => openPicker(item.id)}
                      disabled={busy || uploading}
                    >
                      교체
                    </button>
                    <button
                      type="button"
                      className="icon-button danger"
                      onClick={() => onRemoveItem(item.id)}
                      disabled={busy}
                      title="참고 이미지 제거"
                    >
                      <TrashIcon size={14} />
                    </button>
                  </div>
                </div>

                <p className="reference-summary">{item.analysis.summary}</p>
                <div className="reference-color-row">
                  {item.analysis.dominant_colors.map((color) => (
                    <span
                      key={color}
                      className="reference-color"
                      style={{ background: color }}
                      title={color}
                    />
                  ))}
                  {item.hint && <span className="reference-hint">{item.hint}</span>}
                </div>

                <div className="reference-controls">
                  <label className="reference-control">
                    <span>FOCUS</span>
                    <select
                      className="select-input select-small"
                      value={item.focus}
                      onChange={(event) =>
                        onUpdateItem(item.id, {
                          focus: event.target.value as ReferenceFocus,
                        })
                      }
                      disabled={busy}
                    >
                      {FOCUS_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="reference-control reference-strength">
                    <span>
                      STRENGTH <strong>×{item.strength.toFixed(2)}</strong>
                    </span>
                    <input
                      type="range"
                      min={0}
                      max={1.5}
                      step={0.05}
                      value={item.strength}
                      onChange={(event) =>
                        onUpdateItem(item.id, { strength: Number(event.target.value) })
                      }
                      disabled={busy}
                    />
                  </label>
                </div>
                <p className="reference-focus-hint">
                  {FOCUS_OPTIONS.find((option) => option.value === item.focus)?.hint}
                </p>
                {item.strength === 0 && (
                  <p className="reference-guidance is-warning">
                    Strength가 0이라 이 참고 이미지는 생성에 반영되지 않습니다.
                  </p>
                )}
              </div>
            </article>
          ))}
        </div>
      )}

      {items.length === 0 && (
        <div className="reference-empty">
          <InfoIcon size={16} />
          <span>
            참고 이미지를 1장 이상 선택해야 생성할 수 있습니다. 여러 장을 넣고 각각의 초점과
            강도를 따로 조절할 수 있습니다.
          </span>
        </div>
      )}

      <p className="setting-note reference-note">
        참고 이미지와 모델의 차이가 클수록 강도를 낮추세요. 애니메 계열 모델(예: NoobAI)에 실사
        사진을 넣을 때는 0.4~0.7을 권장합니다. 텍스트 프롬프트와 참고 이미지는 항상 함께
        적용됩니다.
      </p>

      {capabilities && (capabilities.instantid_note || capabilities.pulid_note) && (
        <details className="reference-details">
          <summary>얼굴 동일성(InstantID · PuLID) 안내</summary>
          <p>{capabilities.instantid_note}</p>
          <p>{capabilities.pulid_note}</p>
        </details>
      )}
    </section>
  );
}
