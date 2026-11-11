import { useEffect, useRef, useState } from "react";
import type {
  AppSettings,
  AssetMode,
  HealthResponse,
  ImageSize,
  ModelDownloadItem,
  ModelFile,
  OutputSize,
  PageKind,
  PostProcessMode,
  ResizeFilter,
} from "../types";
import {
  ChevronDownIcon,
  DiceIcon,
  DownloadIcon,
  PaletteIcon,
  RefreshIcon,
  SparkIcon,
  StopIcon,
} from "./Icons";

interface SettingsPanelProps {
  kind: PageKind;
  settings: AppSettings;
  outputSizes: OutputSize[];
  imageSizes: ImageSize[];
  models: HealthResponse["models"] | null;
  modelsError: string | null;
  downloads: ModelDownloadItem[];
  downloadsError: string | null;
  onDownloadModel: (id: string) => void;
  onCancelDownload: (id: string) => void;
  onRefreshModels: () => void;
  onChange: (patch: Partial<AppSettings>) => void;
  onRandomSeed: () => void;
}

function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  return `${value >= 10 || index === 0 ? value.toFixed(0) : value.toFixed(1)} ${units[index]}`;
}

function RangeField({
  label,
  value,
  min,
  max,
  step,
  suffix,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  suffix?: string;
  onChange: (value: number) => void;
}) {
  return (
    <div className="range-field">
      <div className="range-head">
        <span>{label}</span>
        <span className="range-value">
          {value}
          {suffix ?? ""}
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </div>
  );
}

const POSTPROCESS_LABELS: Record<PostProcessMode, string> = {
  quantize: "픽셀 퀀타이즈 · 권장",
  nearest: "니어리스트 · 원본 느낌",
  posterize: "포스터라이즈 · 강한 단순화",
};

const RESIZE_LABELS: Record<ResizeFilter, string> = {
  nearest: "Nearest · 선명한 경계 (권장)",
  box: "Box · 깔끔한 평균",
  lanczos: "Lanczos · 부드러운 디테일",
};

const PALETTE_OPTIONS = [0, 8, 16, 24, 32];

function ModelInfo({ role, model }: { role: string; model?: ModelFile }) {
  if (!model) return null;
  return (
    <div className="model-info">
      <div className="model-info-head">
        <span className="model-info-role">{role}</span>
        <span className="model-info-title">{model.description || "로컬 모델 · 설명 없음"}</span>
      </div>
      <div className="model-tags">
        {model.nsfw && <span className="model-tag is-nsfw">NSFW</span>}
        {model.base_model && <span className="model-tag">{model.base_model}</span>}
        {model.vram_hint && <span className="model-tag">{model.vram_hint}</span>}
        {model.trigger && <span className="model-tag is-trigger">트리거 · {model.trigger}</span>}
        {model.prompt_tip && (
          <span className="model-tag is-tip">권장 프리픽스 · {model.prompt_tip}</span>
        )}
        {model.recommended_strength !== null && (
          <span className="model-tag">권장 ×{model.recommended_strength.toFixed(2)}</span>
        )}
        {model.recommended_steps !== null && model.recommended_cfg !== null && (
          <span className="model-tag">
            권장 {model.recommended_steps} steps · CFG {model.recommended_cfg.toFixed(1)}
          </span>
        )}
      </div>
      {model.features.length > 0 && (
        <div className="model-features">
          {model.features.map((feature) => (
            <span key={feature}>{feature}</span>
          ))}
        </div>
      )}
    </div>
  );
}

export function SettingsPanel({
  kind,
  settings,
  outputSizes,
  imageSizes,
  models,
  modelsError,
  downloads,
  downloadsError,
  onDownloadModel,
  onCancelDownload,
  onRefreshModels,
  onChange,
  onRandomSeed,
}: SettingsPanelProps) {
  const isImage = kind === "image";
  const [catalogOpen, setCatalogOpen] = useState(false);
  const [expandedDownload, setExpandedDownload] = useState<string | null>(null);
  const paletteDisabled = settings.postprocess === "nearest";
  const allCheckpoints = models?.checkpoints ?? [];
  const allLoras = models?.loras ?? [];
  const modelCategory = isImage ? "image" : "pixel";
  const checkpointOptions = allCheckpoints.filter(
    (item) => item.category === modelCategory && item.compatible,
  );
  const loraOptions = allLoras.filter((item) => item.category === modelCategory);
  const selectedCheckpoint = isImage
    ? (settings.imageCheckpoint ?? "")
    : (settings.checkpoint ?? models?.checkpoint.name ?? "");
  const selectedLora = isImage
    ? (settings.imageLora ?? "")
    : settings.lora === null
      ? (models?.lora.name ?? "")
      : settings.lora;
  const checkpointFile = allCheckpoints.find((item) => item.name === selectedCheckpoint);
  const loraFile = selectedLora ? allLoras.find((item) => item.name === selectedLora) : undefined;
  const recommendedSteps = checkpointFile?.recommended_steps ?? 28;
  const recommendedCfg = checkpointFile?.recommended_cfg ?? 6;
  const recommendedLoraStrength = loraFile?.recommended_strength ?? 0.8;
  const recommendationsApplied =
    settings.steps === recommendedSteps &&
    Math.abs(settings.cfg - recommendedCfg) < 0.001 &&
    Math.abs(settings.loraStrength - recommendedLoraStrength) < 0.001;
  const applyRecommended = () =>
    onChange({
      steps: recommendedSteps,
      cfg: recommendedCfg,
      loraStrength: recommendedLoraStrength,
    });

  // Keep the sampling sliders in sync with the selected model stack.  The
  // first resolved key only primes the ref so settings saved in localStorage
  // are not overwritten on page load; every later change (checkpoint, LoRA,
  // or page switch) applies the new model's optimal values automatically.
  const appliedModelKey = useRef<string | null>(null);
  const modelKey = `${kind}:${selectedCheckpoint}:${selectedLora}`;
  useEffect(() => {
    if (!models) return;
    if (appliedModelKey.current === null) {
      appliedModelKey.current = modelKey;
      return;
    }
    if (appliedModelKey.current === modelKey) return;
    appliedModelKey.current = modelKey;
    onChange({
      steps: recommendedSteps,
      cfg: recommendedCfg,
      loraStrength: recommendedLoraStrength,
    });
  }, [
    modelKey,
    models,
    recommendedSteps,
    recommendedCfg,
    recommendedLoraStrength,
    onChange,
  ]);

  const checkpointReady = checkpointOptions.some((item) => item.name === selectedCheckpoint);
  const loraReady = selectedLora === "" || loraOptions.some((item) => item.name === selectedLora);
  const modelReady = checkpointReady && loraReady;
  const modelStateClass = models
    ? modelReady
      ? "ok"
      : "bad"
    : modelsError
      ? "bad"
      : "neutral";
  const modelStateLabel = models
    ? modelReady
      ? "READY"
      : "CHECK"
    : modelsError
      ? "OFFLINE"
      : "LOADING";
  const modelFallback = modelsError ? "백엔드 연결 없음" : "확인 중...";
  const checkpointStateLabel = models
    ? checkpointReady
      ? "READY"
      : checkpointFile
        ? isImage
          ? "NOT IMAGE"
          : "INCOMPATIBLE"
        : "MISSING"
    : modelsError
      ? "OFFLINE"
      : "...";
  const loraStateLabel = models
    ? selectedLora === ""
      ? "OFF"
      : loraReady
        ? "READY"
        : "MISSING"
    : modelsError
      ? "OFFLINE"
      : "...";
  const downloadingCount = downloads.filter((item) => item.status === "downloading").length;
  const installedCount = downloads.filter((item) => item.status === "installed").length;
  const readyCount = downloads.length - installedCount;
  return (
    <section className="panel settings-panel">
      <div className="panel-head">
        <div>
          <span className="eyebrow">02 · SETTINGS</span>
          <h2>{isImage ? "이미지 설정" : "생성 설정"}</h2>
        </div>
        <span className="micro-badge">
          {isImage
            ? `${settings.imageSize}×${settings.imageSize} PX`
            : `${settings.outputSize}×${settings.outputSize} PX`}
        </span>
      </div>

      <div className="model-stack">
        <div className="model-stack-head">
          <span className="field-label">MODEL STACK</span>
          <div className="model-stack-actions">
            <span className={`model-stack-state ${modelStateClass}`}>{modelStateLabel}</span>
            <button
              type="button"
              className="model-refresh"
              onClick={onRefreshModels}
              title="모델 목록 새로고침"
            >
              <RefreshIcon size={13} />
            </button>
          </div>
        </div>

        <div className="model-row">
          <span className="model-role">CHECKPOINT</span>
          {models ? (
            <select
              className="select-input model-select"
              value={selectedCheckpoint}
              onChange={(event) =>
                onChange(
                  isImage
                    ? { imageCheckpoint: event.target.value || null }
                    : { checkpoint: event.target.value || null },
                )
              }
              title={selectedCheckpoint}
            >
              {!selectedCheckpoint && (
                <option value="">
                  {isImage ? "이미지 체크포인트 없음" : "체크포인트 없음"}
                </option>
              )}
              {selectedCheckpoint && !checkpointReady && (
                <option value={selectedCheckpoint}>
                  {selectedCheckpoint} ·{" "}
                  {checkpointFile ? (isImage ? "이미지용 아님" : "픽셀용 아님") : "없음"}
                </option>
              )}
              {checkpointOptions.map((item) => (
                <option key={item.name} value={item.name}>
                  {item.nsfw ? "[NSFW] " : ""}
                  {item.name} · {formatBytes(item.size_bytes)}
                </option>
              ))}
            </select>
          ) : (
            <span className="model-name" title={modelFallback}>
              {selectedCheckpoint || modelFallback}
            </span>
          )}
          <span className={`model-state ${models ? (checkpointReady ? "ok" : "bad") : "neutral"}`}>
            {checkpointStateLabel}
          </span>
        </div>

        <div className="model-row">
          <span className="model-role">LoRA</span>
          {models ? (
            <select
              className="select-input model-select"
              value={selectedLora}
              onChange={(event) =>
                onChange(
                  isImage
                    ? { imageLora: event.target.value }
                    : { lora: event.target.value },
                )
              }
              title={selectedLora || "LoRA 사용 안 함"}
            >
              <option value="">사용 안 함</option>
              {selectedLora && !loraFile && (
                <option value={selectedLora}>{selectedLora} · 없음</option>
              )}
              {selectedLora && loraFile && loraFile.category !== modelCategory && (
                <option value={selectedLora}>{selectedLora} · 다른 페이지용</option>
              )}
              {loraOptions.map((item) => (
                <option key={item.name} value={item.name}>
                  {item.nsfw ? "[NSFW] " : ""}
                  {item.name} · {formatBytes(item.size_bytes)}
                </option>
              ))}
            </select>
          ) : (
            <span className="model-name" title={modelFallback}>
              {selectedLora || "사용 안 함"}
            </span>
          )}
          <span className="model-strength">×{settings.loraStrength.toFixed(2)}</span>
          <span className={`model-state ${models ? (loraReady ? "ok" : "bad") : "neutral"}`}>
            {loraStateLabel}
          </span>
        </div>

        <ModelInfo role="CHECKPOINT" model={checkpointFile} />
        <ModelInfo role="LORA" model={loraFile} />

        <div className="model-catalog">
          <span>
            {isImage ? "이미지" : "픽셀"} 체크포인트 {checkpointOptions.length}개
          </span>
          <span>
            {isImage ? "이미지" : "픽셀"} LoRA {loraOptions.length}개
          </span>
          <span>선택 즉시 적용</span>
        </div>
        <p className="setting-note model-note">
          {isImage
            ? "이미지 페이지에는 SDXL 호환 일반 모델만 표시됩니다. LoRA를 고르면 트리거 단어만 프롬프트 끝에 자동 추가되며, 나머지 문구는 필터링 없이 그대로 ComfyUI로 전달됩니다."
            : "픽셀 페이지에는 파일명에 pixel/sprite 계열 키워드가 있는 모델만 표시됩니다. 다른 페이지용 모델은 목록에서 숨겨집니다."}
        </p>

        <div className="model-downloads">
          <div className="model-download-head">
            <span className="field-label">모델 받기</span>
            <button
              type="button"
              className={`catalog-toggle ${catalogOpen ? "is-open" : ""}`}
              onClick={() => {
                setCatalogOpen((open) => !open);
                if (catalogOpen) setExpandedDownload(null);
              }}
              aria-expanded={catalogOpen}
            >
              {catalogOpen ? "목록 닫기" : `모델 목록 ${downloads.length}`}
              <ChevronDownIcon size={12} />
            </button>
          </div>
          <p className="model-download-summary">
            설치 {installedCount}개 · 받기 가능 {readyCount}개
            {downloadingCount > 0 ? ` · ${downloadingCount}개 받는 중` : ""}
          </p>

          {downloadsError && <p className="setting-note model-download-error">{downloadsError}</p>}

          {catalogOpen && (
            <>
              <div className="model-download-list">
                {downloads.map((item) => {
                  const busy = item.status === "downloading";
                  const expanded = expandedDownload === item.id;
                  return (
                    <div
                      className={`model-download-item is-${item.status} ${
                        expanded ? "is-expanded" : ""
                      }`}
                      key={item.id}
                    >
                      <div className="model-download-row">
                        <button
                          type="button"
                          className="model-download-main"
                          onClick={() => setExpandedDownload(expanded ? null : item.id)}
                          aria-expanded={expanded}
                          title={item.description || item.filename}
                        >
                          <span className={`model-kind is-${item.kind}`}>
                            {item.kind === "checkpoint" ? "CKPT" : "LORA"}
                          </span>
                          <span className="model-download-name">{item.label}</span>
                          <span className="model-download-size">
                            {formatBytes(item.size_bytes)}
                          </span>
                          <ChevronDownIcon size={12} className="model-download-chevron" />
                        </button>
                        {busy ? (
                          <button
                            type="button"
                            className="model-download-btn is-busy"
                            onClick={() => onCancelDownload(item.id)}
                            title="다운로드 취소"
                          >
                            <StopIcon size={12} />
                            {Math.round(item.progress)}%
                          </button>
                        ) : item.status === "installed" ? (
                          <span className="model-download-state ok">설치됨</span>
                        ) : (
                          <button
                            type="button"
                            className="model-download-btn"
                            onClick={() => onDownloadModel(item.id)}
                            title={item.description}
                          >
                            <DownloadIcon size={12} />
                            {item.status === "error"
                              ? "재시도"
                              : item.status === "cancelled" || item.downloaded_bytes > 0
                                ? "이어받기"
                                : "받기"}
                          </button>
                        )}
                      </div>
                      {busy && (
                        <div className="model-progress" aria-hidden="true">
                          <span style={{ width: `${Math.max(1, item.progress)}%` }} />
                        </div>
                      )}
                      {busy && (
                        <div className="model-download-meta">
                          {formatBytes(item.downloaded_bytes)} / {formatBytes(item.size_bytes)} ·{" "}
                          {formatBytes(item.speed_bps)}/s
                        </div>
                      )}
                      {expanded && (
                        <div className="model-download-info">
                          <div className="model-download-filename" title={item.filename}>
                            {item.filename}
                          </div>
                          {!busy && (
                            <div className="model-download-meta">
                              {item.status === "error"
                                ? item.error ?? "다운로드 실패"
                                : item.status === "cancelled"
                                  ? "취소됨 · 이어받기 가능"
                                  : item.status === "installed"
                                    ? "설치 완료"
                                    : item.downloaded_bytes > 0
                                      ? `${formatBytes(item.downloaded_bytes)} 받음 · 이어받기 가능`
                                      : "받기 전"}
                            </div>
                          )}
                          {item.description && (
                            <p className="model-download-desc">{item.description}</p>
                          )}
                          <div className="model-tags">
                            {item.nsfw && <span className="model-tag is-nsfw">NSFW</span>}
                            {item.base_model && (
                              <span className="model-tag">{item.base_model}</span>
                            )}
                            {item.vram_hint && (
                              <span className="model-tag">{item.vram_hint}</span>
                            )}
                            {item.trigger && (
                              <span className="model-tag is-trigger">
                                트리거 · {item.trigger}
                              </span>
                            )}
                            {item.prompt_tip && (
                              <span className="model-tag is-tip">
                                권장 프리픽스 · {item.prompt_tip}
                              </span>
                            )}
                            {item.recommended_steps !== null &&
                              item.recommended_cfg !== null && (
                                <span className="model-tag">
                                  권장 {item.recommended_steps} steps · CFG{" "}
                                  {item.recommended_cfg.toFixed(1)}
                                </span>
                              )}
                            {item.recommended_strength !== null && (
                              <span className="model-tag">
                                권장 ×{item.recommended_strength.toFixed(2)}
                              </span>
                            )}
                          </div>
                          {item.features.length > 0 && (
                            <div className="model-features">
                              {item.features.map((feature) => (
                                <span key={feature}>{feature}</span>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
              {!downloads.length && (
                <p className="setting-note">다운로드 목록을 불러오는 중...</p>
              )}
              <p className="setting-note model-note">
                받은 모델은 ComfyUI 모델 폴더에 저장되고, 완료 후 위 목록에 자동으로 추가됩니다.
              </p>
            </>
          )}
        </div>
      </div>

      {!isImage && (
        <div className="setting-block">
          <span className="field-label">ASSET MODE</span>
          <select
            className="select-input"
            value={settings.mode}
            onChange={(event) => onChange({ mode: event.target.value as AssetMode })}
          >
            <option value="icon">아이콘 · 단일 오브젝트</option>
            <option value="character">캐릭터 · 전신</option>
            <option value="object">게임 오브젝트</option>
            <option value="tile">타일 · 배경</option>
          </select>
          <p className="setting-note">
            모드에 따라 프롬프트와 피사체 크기 보정이 달라집니다.
          </p>
        </div>
      )}

      <div className="setting-block">
        <span className="field-label">
          {isImage ? "IMAGE RESOLUTION" : "OUTPUT RESOLUTION"}
        </span>
        <div className="size-grid">
          {isImage
            ? imageSizes.map((size) => (
                <button
                  key={size}
                  type="button"
                  className={`size-button ${settings.imageSize === size ? "active" : ""}`}
                  onClick={() => onChange({ imageSize: size })}
                >
                  <span>{size}</span>
                  <small>px</small>
                </button>
              ))
            : outputSizes.map((size) => (
                <button
                  key={size}
                  type="button"
                  className={`size-button ${settings.outputSize === size ? "active" : ""}`}
                  onClick={() => onChange({ outputSize: size })}
                >
                  <span>{size}</span>
                  <small>px</small>
                </button>
              ))}
        </div>
        <p className="setting-note">
          {isImage
            ? "SDXL 원본 이미지를 선택한 해상도로 저장합니다. 1024px가 가장 선명합니다."
            : "작을수록 실루엣이 선명하고, 96~128px은 디테일과 팔레트를 더 살립니다."}
        </p>
      </div>

      <div className="setting-block">
        <span className="field-label">SEED</span>
        <div className="seed-row">
          <input
            className="text-input"
            type="text"
            inputMode="numeric"
            placeholder="비우면 랜덤"
            value={settings.seedInput}
            onChange={(event) =>
              onChange({ seedInput: event.target.value.replace(/[^0-9]/g, "") })
            }
          />
          <button type="button" className="icon-button" onClick={onRandomSeed} title="랜덤 시드">
            <DiceIcon size={18} />
          </button>
        </div>
        <p className="setting-note">같은 Seed와 설정이면 같은 결과를 재현할 수 있습니다.</p>
      </div>

      <div className="sampling-head">
        <div className="sampling-title">
          <span className="field-label">SAMPLING</span>
          <small className="sampling-model" title={selectedCheckpoint || "기본 모델"}>
            {checkpointFile?.description || selectedCheckpoint || "기본 모델"}
          </small>
        </div>
        <button
          type="button"
          className={`optimal-button ${recommendationsApplied ? "is-applied" : ""}`}
          onClick={applyRecommended}
          title={`이 모델 기준 STEPS ${recommendedSteps} · CFG ${recommendedCfg.toFixed(1)}${
            loraFile ? ` · LoRA ×${recommendedLoraStrength.toFixed(2)}` : ""
          } 적용`}
        >
          <SparkIcon size={12} />
          {recommendationsApplied ? "최적값 사용 중" : "모델 최적값"}
        </button>
      </div>

      <div className="range-grid">
        <RangeField
          label="STEPS"
          value={settings.steps}
          min={8}
          max={60}
          step={1}
          onChange={(value) => onChange({ steps: value })}
        />
        <RangeField
          label="CFG"
          value={settings.cfg}
          min={1}
          max={15}
          step={0.5}
          onChange={(value) => onChange({ cfg: value })}
        />
        <RangeField
          label="LORA STRENGTH"
          value={settings.loraStrength}
          min={0}
          max={3}
          step={0.05}
          onChange={(value) => onChange({ loraStrength: value })}
        />
      </div>
      <p className="setting-note sampling-note">
        모델 변경 시 자동 적용 ·{" "}
        {checkpointFile?.name ? `${checkpointFile.name} 권장값` : "선택한 모델 권장값"}:{" "}
        <strong>{recommendedSteps} steps</strong> · <strong>CFG {recommendedCfg.toFixed(1)}</strong>
        {loraFile && (
          <>
            {" "}
            · <strong>LoRA ×{recommendedLoraStrength.toFixed(2)}</strong>
          </>
        )}
        {!loraFile && " · LoRA 미사용"}
      </p>

      {!isImage && (
        <>
          <div className="setting-block">
            <div className="field-label-row">
              <span className="field-label">POST-PROCESS</span>
              <PaletteIcon size={15} className="label-icon" />
            </div>
            <select
              className="select-input"
              value={settings.postprocess}
              onChange={(event) => onChange({ postprocess: event.target.value as PostProcessMode })}
            >
              {(Object.keys(POSTPROCESS_LABELS) as PostProcessMode[]).map((mode) => (
                <option key={mode} value={mode}>
                  {POSTPROCESS_LABELS[mode]}
                </option>
              ))}
            </select>
            <div className="inline-row">
              <span className="inline-label">팔레트 색상</span>
              <select
                className="select-input select-small"
                value={settings.paletteColors}
                disabled={paletteDisabled}
                onChange={(event) => onChange({ paletteColors: Number(event.target.value) })}
              >
                {PALETTE_OPTIONS.map((count) => (
                  <option key={count} value={count}>
                    {count === 0 ? "원본 색상" : `${count}색`}
                  </option>
                ))}
              </select>
            </div>
            {paletteDisabled && (
              <p className="setting-note">니어리스트 모드는 팔레트 양자화를 적용하지 않습니다.</p>
            )}
          </div>

          <div className="setting-block">
            <span className="field-label">RESIZE FILTER</span>
            <select
              className="select-input"
              value={settings.resizeFilter}
              onChange={(event) => onChange({ resizeFilter: event.target.value as ResizeFilter })}
            >
              {(Object.keys(RESIZE_LABELS) as ResizeFilter[]).map((filter) => (
                <option key={filter} value={filter}>
                  {RESIZE_LABELS[filter]}
                </option>
              ))}
            </select>
            <p className="setting-note">
              최종 미리보기는 항상 Nearest로 확대됩니다. 타일 모드는 Box가 자동 적용됩니다.
            </p>
          </div>

          <label className="switch-row">
            <div>
              <span className="switch-title">투명 배경</span>
              <small>단색 배경을 감지해 PNG 알파 채널로 저장합니다.</small>
            </div>
            <input
              type="checkbox"
              checked={settings.transparent}
              onChange={(event) => onChange({ transparent: event.target.checked })}
            />
            <span className="switch-track" aria-hidden="true">
              <span className="switch-thumb" />
            </span>
          </label>
        </>
      )}

      {isImage && (
        <div className="prompt-hint settings-hint">
          <PaletteIcon size={15} />
          <span>
            이미지 페이지는 SDXL 원본 PNG를 저장합니다. 팔레트 양자화·배경 제거·니어리스트
            축소는 적용되지 않습니다.
          </span>
        </div>
      )}

      <div className="settings-footer">
        <span>DPM++ 2M Karras</span>
        <span>·</span>
        <span>{settings.steps} steps</span>
        <span>·</span>
        <span>CFG {settings.cfg}</span>
        <span>·</span>
        <span>LoRA {settings.loraStrength.toFixed(2)}</span>
      </div>
    </section>
  );
}
