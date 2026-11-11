import { useCallback, useEffect, useState } from "react";
import { api } from "./api/client";
import { Gallery } from "./components/Gallery";
import { Header } from "./components/Header";
import { PaletteIcon, SparkIcon } from "./components/Icons";
import { PromptPanel } from "./components/PromptPanel";
import { ResultPanel } from "./components/ResultPanel";
import { SettingsPanel } from "./components/SettingsPanel";
import { StatusPanel } from "./components/StatusPanel";
import type {
  AppConfig,
  AppSettings,
  DisplayResult,
  GenerateRequest,
  HealthResponse,
  ImageSize,
  JobView,
  ModelDownloadItem,
  OutputItem,
  PageKind,
  AssetMode,
  OutputSize,
  PostProcessMode,
  ResizeFilter,
} from "./types";

const KEY_PROMPT = "pixelforge.prompt";
const KEY_PROMPT_IMAGE = "pixelforge.prompt.image";
const KEY_NEGATIVE = "pixelforge.negative";
const KEY_NEGATIVE_IMAGE = "pixelforge.negative.image";
const KEY_SETTINGS = "pixelforge.settings";

const DEFAULT_NEGATIVE =
  "blurry, anti-aliased, smooth gradients, photorealistic, realistic texture, excessive details, noise, jpeg artifacts, soft edges, 3d render, text, watermark, signature, frame, border, background scenery, ground shadow, gradient background, textured background";

const DEFAULT_IMAGE_NEGATIVE =
  "blurry, low quality, jpeg artifacts, watermark, text, signature, deformed, bad anatomy, extra limbs, cropped, out of frame";

const DEFAULT_SETTINGS: AppSettings = {
  mode: "icon",
  outputSize: 64,
  seedInput: "",
  steps: 28,
  cfg: 6,
  loraStrength: 0.8,
  transparent: true,
  postprocess: "quantize",
  paletteColors: 16,
  resizeFilter: "nearest",
  checkpoint: null,
  lora: null,
  imageSize: 1024,
  imageCheckpoint: null,
  imageLora: null,
};

const DEFAULT_OUTPUT_SIZES: OutputSize[] = [16, 32, 64, 96, 128];
const IMAGE_SIZES: ImageSize[] = [512, 768, 1024];
const OUTPUT_SIZES: OutputSize[] = [16, 32, 64, 96, 128];
const POSTPROCESS_MODES: PostProcessMode[] = ["quantize", "nearest", "posterize"];
const ASSET_MODES: AssetMode[] = ["icon", "character", "object", "tile"];
const RESIZE_FILTERS: ResizeFilter[] = ["nearest", "box", "lanczos"];

function readStoredSettings(): AppSettings | null {
  try {
    const raw = localStorage.getItem(KEY_SETTINGS);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<AppSettings>;
    const mode = ASSET_MODES.includes(parsed.mode as AssetMode)
      ? (parsed.mode as AssetMode)
      : DEFAULT_SETTINGS.mode;
    const outputSize = OUTPUT_SIZES.includes(parsed.outputSize as OutputSize)
      ? (parsed.outputSize as OutputSize)
      : DEFAULT_SETTINGS.outputSize;
    const postprocess = POSTPROCESS_MODES.includes(parsed.postprocess as PostProcessMode)
      ? (parsed.postprocess as PostProcessMode)
      : DEFAULT_SETTINGS.postprocess;
    const resizeFilter = RESIZE_FILTERS.includes(parsed.resizeFilter as ResizeFilter)
      ? (parsed.resizeFilter as ResizeFilter)
      : DEFAULT_SETTINGS.resizeFilter;
    const imageSize = IMAGE_SIZES.includes(parsed.imageSize as ImageSize)
      ? (parsed.imageSize as ImageSize)
      : DEFAULT_SETTINGS.imageSize;
    return {
      mode,
      outputSize,
      seedInput: typeof parsed.seedInput === "string" ? parsed.seedInput.replace(/[^0-9]/g, "") : "",
      steps: Number.isFinite(parsed.steps) ? Number(parsed.steps) : DEFAULT_SETTINGS.steps,
      cfg: Number.isFinite(parsed.cfg) ? Number(parsed.cfg) : DEFAULT_SETTINGS.cfg,
      loraStrength: Number.isFinite(parsed.loraStrength)
        ? Number(parsed.loraStrength)
        : DEFAULT_SETTINGS.loraStrength,
      transparent:
        typeof parsed.transparent === "boolean" ? parsed.transparent : DEFAULT_SETTINGS.transparent,
      postprocess,
      paletteColors: Number.isFinite(parsed.paletteColors)
        ? Number(parsed.paletteColors)
        : DEFAULT_SETTINGS.paletteColors,
      resizeFilter,
      checkpoint: typeof parsed.checkpoint === "string" ? parsed.checkpoint : null,
      lora: typeof parsed.lora === "string" ? parsed.lora : null,
      imageSize,
      imageCheckpoint:
        typeof parsed.imageCheckpoint === "string" ? parsed.imageCheckpoint : null,
      imageLora: typeof parsed.imageLora === "string" ? parsed.imageLora : null,
    };
  } catch {
    return null;
  }
}

function displayFromOutput(item: OutputItem): DisplayResult {
  const isImage = item.kind === "image";
  const scale = isImage ? 1 : Math.max(1, Math.floor(512 / item.output_size));
  return {
    jobId: item.job_id,
    prompt: item.prompt,
    seed: item.seed,
    createdAt: item.created_at,
    live: false,
    result: {
      original_url: item.original_url,
      cutout_url: item.cutout_url,
      crop_url: item.crop_url,
      pixel_url: item.pixel_url ?? null,
      preview_url: item.preview_url,
      image_url: item.image_url ?? null,
      image_preview_url: isImage ? item.preview_url : null,
      download_url: item.download_url,
      width: item.width,
      height: item.height,
      preview_scale: scale,
      palette_colors: item.palette_colors,
      transparent: item.transparent,
      postprocess: item.postprocess,
      mode: item.mode,
      kind: item.kind ?? "pixel",
      subject_fill: item.subject_fill,
      resize_filter: item.resize_filter,
      quality: item.quality ?? [],
      warnings: [],
      candidates_generated: item.candidates_generated ?? 1,
      candidate_index: item.candidate_index ?? 0,
      candidate_score: item.candidate_score ?? 0,
      panel_suspected: item.panel_suspected ?? false,
    },
  };
}

export default function App() {
  const [storedSettings] = useState<AppSettings | null>(() => readStoredSettings());
  const [hasStoredNegative] = useState(() => localStorage.getItem(KEY_NEGATIVE) !== null);
  const [hasStoredImageNegative] = useState(
    () => localStorage.getItem(KEY_NEGATIVE_IMAGE) !== null,
  );
  const [page, setPage] = useState<PageKind>("pixel");
  const [prompt, setPrompt] = useState(() => localStorage.getItem(KEY_PROMPT) ?? "");
  const [imagePrompt, setImagePrompt] = useState(
    () => localStorage.getItem(KEY_PROMPT_IMAGE) ?? "",
  );
  const [negative, setNegative] = useState(
    () => localStorage.getItem(KEY_NEGATIVE) ?? DEFAULT_NEGATIVE,
  );
  const [imageNegative, setImageNegative] = useState(
    () => localStorage.getItem(KEY_NEGATIVE_IMAGE) ?? DEFAULT_IMAGE_NEGATIVE,
  );
  const [settings, setSettings] = useState<AppSettings>(storedSettings ?? DEFAULT_SETTINGS);
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [downloads, setDownloads] = useState<ModelDownloadItem[]>([]);
  const [downloadsError, setDownloadsError] = useState<string | null>(null);
  const [outputsByPage, setOutputsByPage] = useState<Record<PageKind, OutputItem[]>>({
    pixel: [],
    image: [],
  });
  const [outputsLoading, setOutputsLoading] = useState(true);
  const [jobIds, setJobIds] = useState<Record<PageKind, string | null>>({
    pixel: null,
    image: null,
  });
  const [jobs, setJobs] = useState<Record<PageKind, JobView | null>>({
    pixel: null,
    image: null,
  });
  const [displays, setDisplays] = useState<Record<PageKind, DisplayResult | null>>({
    pixel: null,
    image: null,
  });
  const [errors, setErrors] = useState<Record<PageKind, string | null>>({
    pixel: null,
    image: null,
  });
  const [notices, setNotices] = useState<Record<PageKind, string | null>>({
    pixel: null,
    image: null,
  });
  const [generating, setGenerating] = useState<Record<PageKind, boolean>>({
    pixel: false,
    image: false,
  });

  const activeNegative = page === "image" ? imageNegative : negative;
  const activePrompt = page === "image" ? imagePrompt : prompt;

  useEffect(() => {
    localStorage.setItem(KEY_PROMPT, prompt);
  }, [prompt]);

  useEffect(() => {
    localStorage.setItem(KEY_PROMPT_IMAGE, imagePrompt);
  }, [imagePrompt]);

  useEffect(() => {
    localStorage.setItem(KEY_NEGATIVE, negative);
  }, [negative]);

  useEffect(() => {
    localStorage.setItem(KEY_NEGATIVE_IMAGE, imageNegative);
  }, [imageNegative]);

  useEffect(() => {
    localStorage.setItem(KEY_SETTINGS, JSON.stringify(settings));
  }, [settings]);

  const refreshOutputs = useCallback(async (kind: PageKind) => {
    try {
      const response = await api.getOutputs(24, kind);
      setOutputsByPage((current) => ({ ...current, [kind]: response.items }));
    } catch {
      // The gallery is non-critical; keep the previous list on transient errors.
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    setOutputsLoading(true);
    void refreshOutputs(page).finally(() => {
      if (!cancelled) setOutputsLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [page, refreshOutputs]);

  useEffect(() => {
    let cancelled = false;
    api
      .getConfig()
      .then((loaded) => {
        if (cancelled) return;
        setConfig(loaded);
        if (!storedSettings) {
          setSettings({
            mode: "icon",
            outputSize: loaded.default_output_size,
            seedInput: "",
            steps: loaded.default_steps,
            cfg: loaded.default_cfg,
            loraStrength: loaded.default_lora_strength,
            transparent: loaded.default_transparent,
            postprocess: loaded.default_postprocess,
            paletteColors: loaded.default_palette_colors,
            resizeFilter: loaded.default_resize_filter,
            checkpoint: loaded.checkpoint,
            lora: loaded.lora,
            imageSize: loaded.default_image_size,
            imageCheckpoint: loaded.image_checkpoint || null,
            imageLora: loaded.image_lora || "",
          });
        } else {
          // Keep saved choices, but fill in a model that was never chosen so the
          // dropdown shows the same default the backend will actually use.
          setSettings((previous) => ({
            ...previous,
            checkpoint: previous.checkpoint || loaded.checkpoint,
            imageCheckpoint: previous.imageCheckpoint || loaded.image_checkpoint || null,
          }));
        }
        if (!hasStoredNegative) {
          setNegative(loaded.default_negative_prompt);
        }
        if (!hasStoredImageNegative) {
          setImageNegative(loaded.default_image_negative_prompt || DEFAULT_IMAGE_NEGATIVE);
        }
      })
      .catch(() => {
        // Defaults in the UI still work if config cannot be loaded.
      });
    return () => {
      cancelled = true;
    };
  }, [storedSettings, hasStoredNegative, hasStoredImageNegative]);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const response = await api.getHealth();
        if (!cancelled) {
          setHealth(response);
          setHealthError(null);
        }
      } catch (cause) {
        if (!cancelled) {
          setHealth(null);
          setHealthError(
            cause instanceof Error ? cause.message : "백엔드 상태를 확인하지 못했습니다.",
          );
        }
      }
    };
    void load();
    const timer = window.setInterval(load, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    if (!health) return;
    const imageCheckpoints = health.models.checkpoints.filter(
      (item) => item.category === "image" && item.compatible,
    );
    if (!imageCheckpoints.length) return;
    const preferred = config?.image_checkpoint;
    const fallback =
      imageCheckpoints.find((item) => item.name === preferred) ?? imageCheckpoints[0];
    setSettings((current) =>
      current.imageCheckpoint ? current : { ...current, imageCheckpoint: fallback.name },
    );
  }, [health, config]);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const response = await api.getModelCatalog();
        if (!cancelled) {
          setDownloads(response.items);
          setDownloadsError(null);
        }
      } catch (cause) {
        if (!cancelled) {
          setDownloadsError(
            cause instanceof Error ? cause.message : "모델 다운로드 목록을 확인하지 못했습니다.",
          );
        }
      }
    };
    void load();
    const timer = window.setInterval(load, 3000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const timers: number[] = [];

    const tick = async (kind: PageKind, id: string) => {
      try {
        const next = await api.getJob(id);
        if (cancelled) return;
        setJobs((current) => ({ ...current, [kind]: next }));
        if (next.status === "completed") {
          setGenerating((current) => ({ ...current, [kind]: false }));
          if (next.result) {
            setDisplays((current) => ({
              ...current,
              [kind]: {
                jobId: next.job_id,
                result: next.result,
                prompt: next.request.prompt,
                seed: next.seed_used,
                createdAt: next.completed_at ?? undefined,
                live: true,
                promptPlan: next.prompt_plan,
              },
            }));
          }
          setErrors((current) => ({ ...current, [kind]: null }));
          void refreshOutputs(kind);
        } else if (next.status === "error") {
          setGenerating((current) => ({ ...current, [kind]: false }));
          setErrors((current) => ({
            ...current,
            [kind]: next.error ?? "생성 중 오류가 발생했습니다.",
          }));
          void refreshOutputs(kind);
        } else if (next.status === "cancelled") {
          setGenerating((current) => ({ ...current, [kind]: false }));
          setNotices((current) => ({ ...current, [kind]: "생성이 취소되었습니다." }));
        } else {
          timers.push(window.setTimeout(() => void tick(kind, id), 650));
        }
      } catch (cause) {
        if (cancelled) return;
        setGenerating((current) => ({ ...current, [kind]: false }));
        setErrors((current) => ({
          ...current,
          [kind]: cause instanceof Error ? cause.message : "작업 상태를 가져오지 못했습니다.",
        }));
      }
    };

    (["pixel", "image"] as const).forEach((kind) => {
      const id = jobIds[kind];
      if (id) void tick(kind, id);
    });

    return () => {
      cancelled = true;
      timers.forEach((timer) => window.clearTimeout(timer));
    };
  }, [jobIds.pixel, jobIds.image, refreshOutputs]);

  useEffect(() => {
    if (!notices.pixel) return;
    const timer = window.setTimeout(
      () => setNotices((current) => ({ ...current, pixel: null })),
      4500,
    );
    return () => window.clearTimeout(timer);
  }, [notices.pixel]);

  useEffect(() => {
    if (!notices.image) return;
    const timer = window.setTimeout(
      () => setNotices((current) => ({ ...current, image: null })),
      4500,
    );
    return () => window.clearTimeout(timer);
  }, [notices.image]);

  const submit = useCallback(
    async (overrideSeed?: number) => {
      const targetPage = page;
      const isImage = targetPage === "image";
      if (generating[targetPage]) return;
      const trimmed = (isImage ? imagePrompt : prompt).trim();
      if (!trimmed) {
        setJobs((current) => ({ ...current, [targetPage]: null }));
        setJobIds((current) => ({ ...current, [targetPage]: null }));
        setErrors((current) => ({ ...current, [targetPage]: "프롬프트를 입력해 주세요." }));
        return;
      }

      let seed: number | null = overrideSeed ?? null;
      if (seed === null && settings.seedInput.trim() !== "") {
        const parsed = Number(settings.seedInput);
        if (!Number.isInteger(parsed) || parsed < 0 || parsed > 4_294_967_295) {
          setJobs((current) => ({ ...current, [targetPage]: null }));
          setJobIds((current) => ({ ...current, [targetPage]: null }));
          setErrors((current) => ({
            ...current,
            [targetPage]: "Seed는 0~4294967295 사이의 정수여야 합니다.",
          }));
          return;
        }
        seed = parsed;
      }

      const payload: GenerateRequest = {
        prompt: trimmed,
        negative_prompt: (isImage ? imageNegative : negative).trim() || null,
        mode: isImage ? "icon" : settings.mode,
        output_size: settings.outputSize,
        seed,
        steps: settings.steps,
        cfg: settings.cfg,
        lora_strength: settings.loraStrength,
        transparent: isImage ? false : settings.transparent,
        postprocess: isImage ? "quantize" : settings.postprocess,
        palette_colors: isImage ? 0 : settings.paletteColors,
        resize_filter: isImage ? "nearest" : settings.resizeFilter,
        candidates: isImage ? 1 : undefined,
        checkpoint: isImage ? settings.imageCheckpoint : settings.checkpoint,
        lora: isImage ? (settings.imageLora ?? "") : settings.lora,
        kind: targetPage,
        image_size: settings.imageSize,
      };

      setErrors((current) => ({ ...current, [targetPage]: null }));
      setNotices((current) => ({ ...current, [targetPage]: null }));
      setGenerating((current) => ({ ...current, [targetPage]: true }));
      setJobs((current) => ({ ...current, [targetPage]: null }));
      setJobIds((current) => ({ ...current, [targetPage]: null }));
      setDisplays((current) => ({ ...current, [targetPage]: null }));

      try {
        const response = await api.generate(payload);
        setJobIds((current) => ({ ...current, [targetPage]: response.job_id }));
        try {
          const first = await api.getJob(response.job_id);
          setJobs((current) => ({ ...current, [targetPage]: first }));
        } catch {
          // The polling effect will retry.
        }
      } catch (cause) {
        setGenerating((current) => ({ ...current, [targetPage]: false }));
        setErrors((current) => ({
          ...current,
          [targetPage]: cause instanceof Error ? cause.message : "생성 요청에 실패했습니다.",
        }));
      }
    },
    [page, prompt, imagePrompt, negative, imageNegative, settings, generating],
  );

  const handleCancel = useCallback(async () => {
    const targetPage = page;
    const id = jobIds[targetPage];
    if (!id) return;
    try {
      const response = await api.cancelJob(id);
      setNotices((current) => ({ ...current, [targetPage]: response.message }));
    } catch (cause) {
      setErrors((current) => ({
        ...current,
        [targetPage]: cause instanceof Error ? cause.message : "취소 요청에 실패했습니다.",
      }));
    }
  }, [jobIds, page]);

  const handleRetry = useCallback(() => {
    void submit();
  }, [submit]);

  const handleRegenerate = useCallback(() => {
    if (generating[page]) return;
    const nextSeed = Math.floor(Math.random() * 4_294_967_296);
    setSettings((current) => ({ ...current, seedInput: String(nextSeed) }));
    void submit(nextSeed);
  }, [generating, page, submit]);

  const handleRandomSeed = useCallback(() => {
    setSettings((current) => ({
      ...current,
      seedInput: String(Math.floor(Math.random() * 4_294_967_296)),
    }));
  }, []);

  const handleResetNegative = useCallback(() => {
    if (page === "image") {
      setImageNegative(config?.default_image_negative_prompt ?? DEFAULT_IMAGE_NEGATIVE);
    } else {
      setNegative(config?.default_negative_prompt ?? DEFAULT_NEGATIVE);
    }
  }, [page, config]);

  const handleRefreshModels = useCallback(async () => {
    try {
      const [nextHealth, catalog] = await Promise.all([api.getHealth(), api.getModelCatalog()]);
      setHealth(nextHealth);
      setHealthError(null);
      setDownloads(catalog.items);
      setDownloadsError(null);
    } catch (cause) {
      setDownloadsError(
        cause instanceof Error ? cause.message : "모델 목록을 새로고침하지 못했습니다.",
      );
    }
  }, []);

  const handleDownloadModel = useCallback(async (downloadId: string) => {
    try {
      const item = await api.startModelDownload(downloadId);
      setDownloads((current) =>
        current.some((entry) => entry.id === item.id)
          ? current.map((entry) => (entry.id === item.id ? item : entry))
          : [...current, item],
      );
      setDownloadsError(null);
      setNotices((current) => ({
        ...current,
        [page]: `${item.label} 다운로드를 시작했습니다.`,
      }));
    } catch (cause) {
      setDownloadsError(
        cause instanceof Error ? cause.message : "모델 다운로드를 시작하지 못했습니다.",
      );
    }
  }, [page]);

  const handleCancelDownload = useCallback(async (downloadId: string) => {
    try {
      const item = await api.cancelModelDownload(downloadId);
      setDownloads((current) =>
        current.map((entry) => (entry.id === item.id ? item : entry)),
      );
      setNotices((current) => ({
        ...current,
        [page]: `${item.label} 다운로드를 취소했습니다.`,
      }));
    } catch (cause) {
      setDownloadsError(
        cause instanceof Error ? cause.message : "모델 다운로드를 취소하지 못했습니다.",
      );
    }
  }, [page]);

  const handleSelectOutput = useCallback(
    (item: OutputItem) => {
      const kind = item.kind ?? "pixel";
      if (generating[kind]) return;
      setDisplays((current) => ({ ...current, [kind]: displayFromOutput(item) }));
      setErrors((current) => ({ ...current, [kind]: null }));
      setNotices((current) => ({ ...current, [kind]: null }));
    },
    [generating],
  );

  const outputSizes = config?.output_sizes?.length ? config.output_sizes : DEFAULT_OUTPUT_SIZES;
  const imageSizes = config?.image_sizes?.length ? config.image_sizes : IMAGE_SIZES;
  const backendDown = Boolean(healthError) && !health;
  const comfyDown = health ? !health.comfyui.connected : backendDown;
  const connectionDetail =
    healthError ??
    health?.comfyui.error ??
    "ComfyUI가 시작 중이거나 연결이 끊겼습니다. 잠시 후 자동으로 다시 확인합니다.";
  const headerCheckpoint = page === "image" ? settings.imageCheckpoint : settings.checkpoint;
  const headerLora = page === "image" ? (settings.imageLora ?? "") : settings.lora;

  return (
    <div className="app-shell">
      <Header
        health={health}
        healthError={healthError}
        job={jobs[page]}
        checkpoint={headerCheckpoint}
        lora={headerLora}
      />

      <nav className="mode-tabs" aria-label="생성 모드">
        <button
          type="button"
          className={`mode-tab ${page === "pixel" ? "active" : ""}`}
          aria-pressed={page === "pixel"}
          onClick={() => setPage("pixel")}
        >
          <span className="mode-tab-icon">
            <PaletteIcon size={19} />
          </span>
          <span className="mode-tab-copy">
            <strong>픽셀 생성기</strong>
            <small>도트 스프라이트 · 팔레트 · 자동 검증</small>
          </span>
          <span className="mode-tab-index">01</span>
        </button>
        <button
          type="button"
          className={`mode-tab ${page === "image" ? "active" : ""}`}
          aria-pressed={page === "image"}
          onClick={() => setPage("image")}
        >
          <span className="mode-tab-icon">
            <SparkIcon size={19} />
          </span>
          <span className="mode-tab-copy">
            <strong>이미지 생성기</strong>
            <small>SDXL 원본 이미지 · 픽셀 후처리 없음</small>
          </span>
          <span className="mode-tab-index">02</span>
        </button>
      </nav>

      {comfyDown && (
        <div className={`connection-banner ${backendDown ? "danger" : ""}`}>
          <span className="banner-dot" />
          <div>
            <strong>
              {backendDown
                ? "백엔드 서버에 연결할 수 없습니다."
                : "ComfyUI 연결을 기다리는 중입니다."}
            </strong>
            <span>{connectionDetail}</span>
          </div>
        </div>
      )}

      <main className="workspace">
        <div className="left-column">
          <PromptPanel
            kind={page}
            prompt={activePrompt}
            negativePrompt={activeNegative}
            onPromptChange={page === "image" ? setImagePrompt : setPrompt}
            onNegativeChange={page === "image" ? setImageNegative : setNegative}
            onResetNegative={handleResetNegative}
            onGenerate={() => void submit()}
            onCancel={() => void handleCancel()}
            busy={generating[page]}
            canGenerate={activePrompt.trim().length > 0}
          />
          <StatusPanel
            kind={page}
            job={jobs[page]}
            jobId={jobIds[page]}
            error={errors[page]}
            notice={notices[page]}
            onRetry={handleRetry}
            onCancel={() => void handleCancel()}
          />
          <SettingsPanel
            kind={page}
            settings={settings}
            outputSizes={outputSizes}
            imageSizes={imageSizes}
            models={health?.models ?? null}
            modelsError={healthError}
            downloads={downloads}
            downloadsError={downloadsError}
            onDownloadModel={(id) => void handleDownloadModel(id)}
            onCancelDownload={(id) => void handleCancelDownload(id)}
            onRefreshModels={() => void handleRefreshModels()}
            onChange={(patch) => setSettings((current) => ({ ...current, ...patch }))}
            onRandomSeed={handleRandomSeed}
          />
        </div>

        <div className="right-column">
          <ResultPanel
            kind={page}
            display={displays[page]}
            busy={generating[page]}
            onRegenerate={handleRegenerate}
          />
          <Gallery
            kind={page}
            items={outputsByPage[page]}
            loading={outputsLoading}
            disabled={generating[page]}
            onSelect={handleSelectOutput}
          />
        </div>
      </main>

      <footer className="app-footer">
        <span>PIXELFORGE LOCAL v{config?.app_version ?? "1.0.0"}</span>
        <span>100% LOCAL · COMFYUI + SDXL</span>
        <span>{config?.comfyui_url ?? "http://127.0.0.1:8188"}</span>
      </footer>
    </div>
  );
}
