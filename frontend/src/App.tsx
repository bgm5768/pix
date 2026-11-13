import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api/client";
import { ComicCuts } from "./components/ComicCuts";
import { ComicPagePanel } from "./components/ComicPagePanel";
import { ComicStudioPanel } from "./components/ComicStudioPanel";
import { Gallery } from "./components/Gallery";
import { Header } from "./components/Header";
import { BackendOverride } from "./components/BackendOverride";
import { JobList } from "./components/JobList";
import { BookIcon, ImageIcon, PaletteIcon, SparkIcon } from "./components/Icons";
import { ModelPicker } from "./components/ModelPicker";
import { PromptPanel } from "./components/PromptPanel";
import { ReferencePanel } from "./components/ReferencePanel";
import { ResourceBar } from "./components/ResourceBar";
import { ResultPanel } from "./components/ResultPanel";
import { SettingsPanel } from "./components/SettingsPanel";
import { StatusPanel } from "./components/StatusPanel";
import type {
  AppConfig,
  AppSettings,
  DisplayResult,
  GenerateRequest,
  HealthResponse,
  IdentityEngine,
  IdentityMethod,
  ImageSize,
  JobStatus,
  JobView,
  ModelDownloadItem,
  ModelFile,
  OutputItem,
  PageKind,
  AssetMode,
  OutputSize,
  PostProcessMode,
  ReferenceAsset,
  ReferenceCapabilities,
  ReferenceFocus,
  ReferenceItem,
  ResizeFilter,
  SystemStatusResponse,
  TranslationPreview,
} from "./types";

const KEY_PROMPT = "pixelforge.prompt";
const KEY_PROMPT_IMAGE = "pixelforge.prompt.image";
const KEY_PROMPT_REFERENCE = "pixelforge.prompt.reference";
const KEY_NEGATIVE = "pixelforge.negative";
const KEY_NEGATIVE_IMAGE = "pixelforge.negative.image";
const KEY_NEGATIVE_REFERENCE = "pixelforge.negative.reference";
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
  imageWidth: null,
  imageHeight: null,
  referenceSize: 1024,
  referenceCheckpoint: null,
  referenceLora: null,
  referenceStrength: 0.85,
  referenceFocus: "appearance",
  identityEngine: "none",
  identityMethod: "fidelity",
  identityWeight: 0.85,
  identityControlWeight: 0.5,
  identityNoise: 0.35,
  identityIncludeStyle: false,
  identityImage: null,
  autoTranslate: true,
};

const EMPTY_TRANSLATION: TranslationPreview = {
  source: "",
  text: "",
  status: "idle",
  translated: false,
  error: null,
};

const DEFAULT_OUTPUT_SIZES: OutputSize[] = [16, 32, 64, 96, 128];
const IMAGE_SIZES: ImageSize[] = [512, 768, 1024];
const OUTPUT_SIZES: OutputSize[] = [16, 32, 64, 96, 128];
const POSTPROCESS_MODES: PostProcessMode[] = ["quantize", "nearest", "posterize"];
const ASSET_MODES: AssetMode[] = ["icon", "character", "object", "tile"];
const RESIZE_FILTERS: ResizeFilter[] = ["nearest", "box", "lanczos"];

const JOB_HISTORY_LIMIT = 14;
const ACTIVE_JOB_STATUSES: JobStatus[] = [
  "queued",
  "preparing",
  "generating",
  "postprocessing",
];

function isActiveJob(status: JobStatus): boolean {
  return ACTIVE_JOB_STATUSES.includes(status);
}

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
    const referenceSize = IMAGE_SIZES.includes(parsed.referenceSize as ImageSize)
      ? (parsed.referenceSize as ImageSize)
      : DEFAULT_SETTINGS.referenceSize;
    const referenceFocus = ["appearance", "face", "style", "pose", "composition"].includes(
      String(parsed.referenceFocus),
    )
      ? (parsed.referenceFocus as ReferenceFocus)
      : DEFAULT_SETTINGS.referenceFocus;
    const identityEngine = ["none", "instantid", "pulid"].includes(
      String(parsed.identityEngine),
    )
      ? (parsed.identityEngine as IdentityEngine)
      : DEFAULT_SETTINGS.identityEngine;
    const identityMethod = ["fidelity", "style", "neutral"].includes(
      String(parsed.identityMethod),
    )
      ? (parsed.identityMethod as IdentityMethod)
      : DEFAULT_SETTINGS.identityMethod;
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
      imageWidth:
        typeof parsed.imageWidth === "number" && parsed.imageWidth > 0
          ? parsed.imageWidth
          : null,
      imageHeight:
        typeof parsed.imageHeight === "number" && parsed.imageHeight > 0
          ? parsed.imageHeight
          : null,
      referenceSize,
      referenceCheckpoint:
        typeof parsed.referenceCheckpoint === "string" ? parsed.referenceCheckpoint : null,
      referenceLora: typeof parsed.referenceLora === "string" ? parsed.referenceLora : null,
      referenceStrength: Number.isFinite(parsed.referenceStrength)
        ? Number(parsed.referenceStrength)
        : DEFAULT_SETTINGS.referenceStrength,
      referenceFocus,
      identityEngine,
      identityMethod,
      identityWeight: Number.isFinite(parsed.identityWeight)
        ? Number(parsed.identityWeight)
        : DEFAULT_SETTINGS.identityWeight,
      identityControlWeight: Number.isFinite(parsed.identityControlWeight)
        ? Number(parsed.identityControlWeight)
        : DEFAULT_SETTINGS.identityControlWeight,
      identityNoise: Number.isFinite(parsed.identityNoise)
        ? Number(parsed.identityNoise)
        : DEFAULT_SETTINGS.identityNoise,
      identityIncludeStyle:
        typeof parsed.identityIncludeStyle === "boolean"
          ? parsed.identityIncludeStyle
          : DEFAULT_SETTINGS.identityIncludeStyle,
      identityImage:
        typeof parsed.identityImage === "string" ? parsed.identityImage : null,
      autoTranslate:
        typeof parsed.autoTranslate === "boolean" ? parsed.autoTranslate : true,
    };
  } catch {
    return null;
  }
}

function displayFromOutput(item: OutputItem): DisplayResult {
  const isNative = item.kind === "image" || item.kind === "reference";
  const scale = isNative ? 1 : Math.max(1, Math.floor(512 / item.output_size));
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
      image_preview_url: isNative ? item.preview_url : null,
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
      references: item.references ?? [],
      identity: item.identity ?? null,
      details: item.details ?? null,
    },
  };
}

export default function App() {
  const [storedSettings] = useState<AppSettings | null>(() => readStoredSettings());
  const [hasStoredNegative] = useState(() => localStorage.getItem(KEY_NEGATIVE) !== null);
  const [hasStoredImageNegative] = useState(
    () => localStorage.getItem(KEY_NEGATIVE_IMAGE) !== null,
  );
  const [hasStoredReferenceNegative] = useState(
    () => localStorage.getItem(KEY_NEGATIVE_REFERENCE) !== null,
  );
  const [page, setPage] = useState<PageKind>("pixel");
  const [prompt, setPrompt] = useState(() => localStorage.getItem(KEY_PROMPT) ?? "");
  const [imagePrompt, setImagePrompt] = useState(
    () => localStorage.getItem(KEY_PROMPT_IMAGE) ?? "",
  );
  const [referencePrompt, setReferencePrompt] = useState(
    () => localStorage.getItem(KEY_PROMPT_REFERENCE) ?? "",
  );
  const [negative, setNegative] = useState(
    () => localStorage.getItem(KEY_NEGATIVE) ?? DEFAULT_NEGATIVE,
  );
  const [imageNegative, setImageNegative] = useState(
    () => localStorage.getItem(KEY_NEGATIVE_IMAGE) ?? DEFAULT_IMAGE_NEGATIVE,
  );
  const [referenceNegative, setReferenceNegative] = useState(
    () => localStorage.getItem(KEY_NEGATIVE_REFERENCE) ?? DEFAULT_IMAGE_NEGATIVE,
  );
  const [settings, setSettings] = useState<AppSettings>(storedSettings ?? DEFAULT_SETTINGS);
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [system, setSystem] = useState<SystemStatusResponse | null>(null);
  const [jobHistory, setJobHistory] = useState<JobView[]>([]);
  const [jobHistoryLoading, setJobHistoryLoading] = useState(true);
  const restoredJobsRef = useRef(false);
  const [downloads, setDownloads] = useState<ModelDownloadItem[]>([]);
  const [downloadsError, setDownloadsError] = useState<string | null>(null);
  const [outputsByPage, setOutputsByPage] = useState<Record<PageKind, OutputItem[]>>({
    pixel: [],
    image: [],
    reference: [],
  });
  const [outputsLoading, setOutputsLoading] = useState(true);
  const [jobIds, setJobIds] = useState<Record<PageKind, string | null>>({
    pixel: null,
    image: null,
    reference: null,
  });
  const [jobs, setJobs] = useState<Record<PageKind, JobView | null>>({
    pixel: null,
    image: null,
    reference: null,
  });
  const [displays, setDisplays] = useState<Record<PageKind, DisplayResult | null>>({
    pixel: null,
    image: null,
    reference: null,
  });
  const [errors, setErrors] = useState<Record<PageKind, string | null>>({
    pixel: null,
    image: null,
    reference: null,
  });
  const [notices, setNotices] = useState<Record<PageKind, string | null>>({
    pixel: null,
    image: null,
    reference: null,
  });
  const [generating, setGenerating] = useState<Record<PageKind, boolean>>({
    pixel: false,
    image: false,
    reference: false,
  });
  const [nativeTranslation, setNativeTranslation] =
    useState<TranslationPreview>(EMPTY_TRANSLATION);
  const [referenceItems, setReferenceItems] = useState<ReferenceItem[]>([]);
  const [referenceSamples, setReferenceSamples] = useState<ReferenceAsset[]>([]);
  const [referenceSamplesLoading, setReferenceSamplesLoading] = useState(false);
  const [referenceCapabilities, setReferenceCapabilities] =
    useState<ReferenceCapabilities | null>(null);
  const [referenceCapabilitiesLoading, setReferenceCapabilitiesLoading] = useState(false);
  const [referenceCapabilitiesError, setReferenceCapabilitiesError] = useState<string | null>(
    null,
  );
  const [referenceUploading, setReferenceUploading] = useState(false);
  const [referenceUploadError, setReferenceUploadError] = useState<string | null>(null);
  const [detailsJobId, setDetailsJobId] = useState<string | null>(null);
  const [comicStudioOpen, setComicStudioOpen] = useState(false);

  const activeNegative =
    page === "image"
      ? imageNegative
      : page === "reference"
        ? referenceNegative
        : negative;
  const activePrompt =
    page === "image" ? imagePrompt : page === "reference" ? referencePrompt : prompt;
  const isNativePage = page === "image" || page === "reference";

  /**
   * Merge a fresh /api/jobs response. Any job that is still queued/running is
   * adopted by its page, so a page refresh (or a second tab) reconnects to the
   * live progress instead of starting from an empty status panel.
   */
  const applyJobList = useCallback((items: JobView[]) => {
    setJobHistory(items);

    const activeByKind: Partial<Record<PageKind, JobView>> = {};
    for (const job of items) {
      if (isActiveJob(job.status) && !activeByKind[job.request.kind]) {
        activeByKind[job.request.kind] = job;
      }
    }

    // On the first list load, jump to the page that owns the live job so a
    // refresh during generation lands directly on its progress panel.
    if (!restoredJobsRef.current) {
      restoredJobsRef.current = true;
      const running =
        items.find((job) =>
          ["preparing", "generating", "postprocessing"].includes(job.status),
        ) ?? items.find((job) => job.status === "queued");
      if (running) {
        setPage((current) => (activeByKind[current] ? current : running.request.kind));
      }
    }

    if (!activeByKind.pixel && !activeByKind.image && !activeByKind.reference) return;

    setJobIds((current) => {
      const next = { ...current };
      (["pixel", "image", "reference"] as const).forEach((kind) => {
        const active = activeByKind[kind];
        if (!next[kind] && active) next[kind] = active.job_id;
      });
      return next.pixel === current.pixel &&
        next.image === current.image &&
        next.reference === current.reference
        ? current
        : next;
    });
    setJobs((current) => {
      const next = { ...current };
      (["pixel", "image", "reference"] as const).forEach((kind) => {
        if (!next[kind] && activeByKind[kind]) next[kind] = activeByKind[kind] ?? null;
      });
      return next.pixel === current.pixel &&
        next.image === current.image &&
        next.reference === current.reference
        ? current
        : next;
    });
    setGenerating((current) => {
      const next = { ...current };
      (["pixel", "image", "reference"] as const).forEach((kind) => {
        if (activeByKind[kind]) next[kind] = true;
      });
      return next.pixel === current.pixel &&
        next.image === current.image &&
        next.reference === current.reference
        ? current
        : next;
    });
  }, []);

  const refreshJobHistory = useCallback(async () => {
    try {
      const response = await api.getJobs(JOB_HISTORY_LIMIT);
      applyJobList(response.items);
    } catch {
      // The next poll retries; keep the last known list visible.
    } finally {
      setJobHistoryLoading(false);
    }
  }, [applyJobList]);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const response = await api.getJobs(JOB_HISTORY_LIMIT);
        if (!cancelled) applyJobList(response.items);
      } catch {
        // The next poll retries; keep the last known list visible.
      } finally {
        if (!cancelled) setJobHistoryLoading(false);
      }
    };
    void load();
    const timer = window.setInterval(load, 3500);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [applyJobList]);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const response = await api.getSystem();
        if (!cancelled) setSystem(response);
      } catch {
        // Keep the last sample; the next tick will update it.
      }
    };
    void load();
    const timer = window.setInterval(load, 2500);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

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
    localStorage.setItem(KEY_PROMPT_REFERENCE, referencePrompt);
  }, [referencePrompt]);

  useEffect(() => {
    localStorage.setItem(KEY_NEGATIVE_REFERENCE, referenceNegative);
  }, [referenceNegative]);

  useEffect(() => {
    localStorage.setItem(KEY_SETTINGS, JSON.stringify(settings));
  }, [settings]);

  useEffect(() => {
    if (!isNativePage || !settings.autoTranslate) {
      setNativeTranslation(EMPTY_TRANSLATION);
      return;
    }
    const source = activePrompt.trim();
    if (!source) {
      setNativeTranslation(EMPTY_TRANSLATION);
      return;
    }
    if (!/[가-힣]/.test(source)) {
      setNativeTranslation({
        source,
        text: source,
        status: "idle",
        translated: false,
        error: null,
      });
      return;
    }

    let cancelled = false;
    const timer = window.setTimeout(() => {
      setNativeTranslation({
        source,
        text: "",
        status: "loading",
        translated: false,
        error: null,
      });
      api
        .translatePrompt(source)
        .then((result) => {
          if (cancelled) return;
          setNativeTranslation({
            source,
            text: result.text || source,
            status: result.error ? "error" : "done",
            translated: result.translated,
            error: result.error,
          });
        })
        .catch((cause) => {
          if (cancelled) return;
          setNativeTranslation({
            source,
            text: "",
            status: "error",
            translated: false,
            error: cause instanceof Error ? cause.message : "번역 요청에 실패했습니다.",
          });
        });
    }, 350);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [page, isNativePage, activePrompt, settings.autoTranslate]);

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
            imageWidth: null,
            imageHeight: null,
            referenceSize: loaded.reference_default_size ?? loaded.default_image_size,
            referenceCheckpoint: loaded.reference_checkpoint || loaded.image_checkpoint || null,
            referenceLora: loaded.reference_lora || "",
            referenceStrength: loaded.reference_default_strength ?? 0.85,
            referenceFocus: loaded.reference_default_focus ?? "appearance",
            identityEngine: "none",
            identityMethod: "fidelity",
            identityWeight: 0.85,
            identityControlWeight: 0.5,
            identityNoise: 0.35,
            identityIncludeStyle: false,
            identityImage: null,
            autoTranslate: true,
          });
        } else {
          // Keep saved choices, but fill in a model that was never chosen so the
          // dropdown shows the same default the backend will actually use.
          setSettings((previous) => ({
            ...previous,
            checkpoint: previous.checkpoint || loaded.checkpoint,
            imageCheckpoint: previous.imageCheckpoint || loaded.image_checkpoint || null,
            referenceCheckpoint:
              previous.referenceCheckpoint ||
              loaded.reference_checkpoint ||
              loaded.image_checkpoint ||
              null,
          }));
        }
        if (!hasStoredNegative) {
          setNegative(loaded.default_negative_prompt);
        }
        if (!hasStoredImageNegative) {
          setImageNegative(loaded.default_image_negative_prompt || DEFAULT_IMAGE_NEGATIVE);
        }
        if (!hasStoredReferenceNegative) {
          setReferenceNegative(
            loaded.default_image_negative_prompt || DEFAULT_IMAGE_NEGATIVE,
          );
        }
      })
      .catch(() => {
        // Defaults in the UI still work if config cannot be loaded.
      });
    return () => {
      cancelled = true;
    };
  }, [
    storedSettings,
    hasStoredNegative,
    hasStoredImageNegative,
    hasStoredReferenceNegative,
  ]);

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
    // The reference page has its own checkpoint default; only fill it once the
    // server config is known so a stale health-only guess cannot win.
    if (config?.reference_checkpoint) {
      const referenceFallback =
        imageCheckpoints.find((item) => item.name === config.reference_checkpoint) ?? fallback;
      setSettings((current) =>
        current.referenceCheckpoint
          ? current
          : { ...current, referenceCheckpoint: referenceFallback.name },
      );
    }
  }, [health, config]);

  const referenceCheckpoint = settings.referenceCheckpoint ?? null;

  const loadReferenceCapabilities = useCallback(async () => {
    setReferenceCapabilitiesLoading(true);
    try {
      const capabilities = await api.getReferenceCapabilities(referenceCheckpoint);
      setReferenceCapabilities(capabilities);
      setReferenceCapabilitiesError(null);
    } catch (cause) {
      setReferenceCapabilities(null);
      setReferenceCapabilitiesError(
        cause instanceof Error ? cause.message : "IP-Adapter 상태를 확인하지 못했습니다.",
      );
    } finally {
      setReferenceCapabilitiesLoading(false);
    }
  }, [referenceCheckpoint]);

  const loadReferenceSamples = useCallback(async () => {
    setReferenceSamplesLoading(true);
    try {
      const response = await api.getReferenceSamples();
      setReferenceSamples(response.items);
    } catch {
      // Samples are optional; the upload path still works without them.
    } finally {
      setReferenceSamplesLoading(false);
    }
  }, []);

  useEffect(() => {
    if (page !== "reference") return;
    void loadReferenceCapabilities();
  }, [page, loadReferenceCapabilities]);

  useEffect(() => {
    if (page !== "reference") return;
    void loadReferenceSamples();
  }, [page, loadReferenceSamples]);

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
          void refreshJobHistory();
        } else if (next.status === "error") {
          setGenerating((current) => ({ ...current, [kind]: false }));
          setErrors((current) => ({
            ...current,
            [kind]: next.error ?? "생성 중 오류가 발생했습니다.",
          }));
          void refreshOutputs(kind);
          void refreshJobHistory();
        } else if (next.status === "cancelled") {
          setGenerating((current) => ({ ...current, [kind]: false }));
          setNotices((current) => ({ ...current, [kind]: "생성이 취소되었습니다." }));
          void refreshJobHistory();
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

    (["pixel", "image", "reference"] as const).forEach((kind) => {
      const id = jobIds[kind];
      if (id) void tick(kind, id);
    });

    return () => {
      cancelled = true;
      timers.forEach((timer) => window.clearTimeout(timer));
    };
  }, [jobIds.pixel, jobIds.image, jobIds.reference, refreshOutputs, refreshJobHistory]);

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

  useEffect(() => {
    if (!notices.reference) return;
    const timer = window.setTimeout(
      () => setNotices((current) => ({ ...current, reference: null })),
      4500,
    );
    return () => window.clearTimeout(timer);
  }, [notices.reference]);

  const buildPayload = useCallback(
    async (promptText: string, seedOverride: number | null = null): Promise<GenerateRequest> => {
      const targetPage = page;
      const isImage = targetPage === "image";
      const isReference = targetPage === "reference";
      const isNative = isImage || isReference;
      const trimmed = promptText.trim();

      let seed: number | null = seedOverride;
      if (seed === null && settings.seedInput.trim() !== "") {
        const parsed = Number(settings.seedInput);
        if (Number.isInteger(parsed) && parsed >= 0 && parsed <= 4_294_967_295) {
          seed = parsed;
        }
      }

      let promptForGeneration = trimmed;
      let translatePrompt = false;
      if (isNative && settings.autoTranslate) {
        translatePrompt = true;
        if (/[가-힣]/.test(trimmed)) {
          try {
            const ready =
              nativeTranslation.source === trimmed &&
              nativeTranslation.status === "done" &&
              nativeTranslation.translated &&
              nativeTranslation.text
                ? nativeTranslation.text
                : null;
            if (ready) {
              promptForGeneration = ready;
            } else {
              const result = await api.translatePrompt(trimmed);
              if (result.text && !result.error) {
                promptForGeneration = result.text;
              }
            }
          } catch {
            // The backend translates again when translate_prompt is true.
          }
        }
      }

      return {
        prompt: promptForGeneration,
        negative_prompt: (
          isImage ? imageNegative : isReference ? referenceNegative : negative
        ).trim() || null,
        mode: isNative ? "icon" : settings.mode,
        output_size: settings.outputSize,
        seed,
        steps: settings.steps,
        cfg: settings.cfg,
        lora_strength: settings.loraStrength,
        transparent: isNative ? false : settings.transparent,
        postprocess: isNative ? "quantize" : settings.postprocess,
        palette_colors: isNative ? 0 : settings.paletteColors,
        resize_filter: isNative ? "nearest" : settings.resizeFilter,
        candidates: isNative ? 1 : undefined,
        checkpoint: isReference
          ? settings.referenceCheckpoint
          : isImage
            ? settings.imageCheckpoint
            : settings.checkpoint,
        lora: isReference
          ? (settings.referenceLora ?? "")
          : isImage
            ? (settings.imageLora ?? "")
            : settings.lora,
        kind: targetPage,
        image_size: isReference ? settings.referenceSize : settings.imageSize,
        image_width: isNative ? settings.imageWidth : null,
        image_height: isNative ? settings.imageHeight : null,
        translate_prompt: translatePrompt,
        reference_images: isReference
          ? referenceItems.map((item) => ({
              asset_id: item.id,
              strength: item.strength,
              focus: item.focus,
            }))
          : undefined,
        identity_engine: isReference ? settings.identityEngine : "none",
        identity_image:
          isReference && settings.identityEngine !== "none"
            ? (settings.identityImage ?? null)
            : null,
        identity_weight: settings.identityWeight,
        identity_method: settings.identityMethod,
        identity_control_weight: settings.identityControlWeight,
        identity_noise: settings.identityNoise,
        identity_include_style: settings.identityIncludeStyle,
      };
    },
    [
      page,
      settings,
      referenceItems,
      nativeTranslation,
      imageNegative,
      referenceNegative,
      negative,
    ],
  );

  const submit = useCallback(
    async (overrideSeed?: number) => {
      const targetPage = page;
      const isImage = targetPage === "image";
      const isReference = targetPage === "reference";
      if (generating[targetPage]) return;
      const trimmed = (
        isImage ? imagePrompt : isReference ? referencePrompt : prompt
      ).trim();
      if (!trimmed) {
        setJobs((current) => ({ ...current, [targetPage]: null }));
        setJobIds((current) => ({ ...current, [targetPage]: null }));
        setErrors((current) => ({ ...current, [targetPage]: "프롬프트를 입력해 주세요." }));
        return;
      }
      if (isReference && referenceItems.length === 0) {
        setErrors((current) => ({
          ...current,
          [targetPage]: "참고 이미지를 1장 이상 선택해 주세요.",
        }));
        return;
      }
      if (isReference && settings.identityEngine !== "none") {
        const identityAsset = settings.identityImage;
        const known = referenceItems.some((item) => item.id === identityAsset);
        if (!identityAsset || !known) {
          setErrors((current) => ({
            ...current,
            [targetPage]: "얼굴을 고정할 참고 이미지를 선택해 주세요.",
          }));
          return;
        }
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

      const payload = await buildPayload(trimmed, seed);

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
    [
      page,
      prompt,
      imagePrompt,
      referencePrompt,
      negative,
      imageNegative,
      referenceNegative,
      settings,
      generating,
      referenceItems,
      buildPayload,
    ],
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

  const handleCancelJob = useCallback(
    async (jobId: string) => {
      const target = jobHistory.find((job) => job.job_id === jobId);
      const kind = target?.request.kind ?? page;
      try {
        const response = await api.cancelJob(jobId);
        setJobHistory((current) =>
          current.map((job) => {
            if (job.job_id !== jobId) return job;
            return response.status === "cancelled"
              ? { ...job, status: "cancelled", stage_message: "취소됨" }
              : { ...job, stage_message: "취소 요청 중..." };
          }),
        );
        setJobs((current) => {
          const tracked = current[kind];
          if (!tracked || tracked.job_id !== jobId) return current;
          return {
            ...current,
            [kind]:
              response.status === "cancelled"
                ? { ...tracked, status: "cancelled", stage_message: "취소됨" }
                : { ...tracked, stage_message: "취소 요청 중..." },
          };
        });
        setNotices((current) => ({ ...current, [kind]: response.message }));
        void refreshJobHistory();
      } catch (cause) {
        setErrors((current) => ({
          ...current,
          [kind]: cause instanceof Error ? cause.message : "취소 요청에 실패했습니다.",
        }));
      }
    },
    [jobHistory, page, refreshJobHistory],
  );

  const handleSelectJob = useCallback((job: JobView) => {
    const kind = job.request.kind;
    if (isActiveJob(job.status)) {
      // Jump to the page that owns the live job so its progress panel is shown.
      setPage(kind);
      setJobs((current) => ({ ...current, [kind]: job }));
      setJobIds((current) => ({ ...current, [kind]: job.job_id }));
      setGenerating((current) => ({ ...current, [kind]: true }));
      setErrors((current) => ({ ...current, [kind]: null }));
      setNotices((current) => ({ ...current, [kind]: null }));
      return;
    }
    if (job.status !== "completed" || !job.result) return;
    setPage(kind);
    setDisplays((current) => ({
      ...current,
      [kind]: {
        jobId: job.job_id,
        result: job.result,
        prompt: job.request.prompt,
        seed: job.seed_used,
        createdAt: job.completed_at ?? undefined,
        live: true,
        promptPlan: job.prompt_plan,
      },
    }));
    setErrors((current) => ({ ...current, [kind]: null }));
    setNotices((current) => ({ ...current, [kind]: null }));
  }, []);

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
    } else if (page === "reference") {
      setReferenceNegative(config?.default_image_negative_prompt ?? DEFAULT_IMAGE_NEGATIVE);
    } else {
      setNegative(config?.default_negative_prompt ?? DEFAULT_NEGATIVE);
    }
  }, [page, config]);

  const handleSelectModel = useCallback(
    (model: ModelFile) => {
      const isReference = page === "reference";
      setSettings((current) => ({
        ...current,
        ...(isReference
          ? { referenceCheckpoint: model.name }
          : { imageCheckpoint: model.name }),
        steps: model.recommended_steps ?? current.steps,
        cfg: model.recommended_cfg ?? current.cfg,
      }));
      setNotices((current) => ({
        ...current,
        [page]: `${model.name} 로 바꿨습니다.`,
      }));
    },
    [page],
  );

  const handleAddReference = useCallback(
    (asset: ReferenceAsset) => {
      setReferenceUploadError(null);
      setReferenceItems((current) => {
        if (current.some((item) => item.id === asset.id)) return current;
        if (current.length >= (config?.reference_max_references ?? 5)) return current;
        return [
          ...current,
          {
            ...asset,
            focus: settings.referenceFocus,
            strength: settings.referenceStrength,
          },
        ];
      });
    },
    [config, settings.referenceFocus, settings.referenceStrength],
  );

  const handleRemoveReference = useCallback((assetId: string) => {
    setReferenceItems((current) => current.filter((item) => item.id !== assetId));
    setSettings((current) =>
      current.identityImage === assetId
        ? { ...current, identityImage: null }
        : current,
    );
  }, []);

  const handleIdentityChange = useCallback(
    (patch: {
      engine?: IdentityEngine;
      method?: IdentityMethod;
      weight?: number;
      controlWeight?: number;
      noise?: number;
      includeStyle?: boolean;
      image?: string | null;
    }) => {
      setSettings((current) => {
        const next = { ...current };
        if (patch.engine !== undefined) next.identityEngine = patch.engine;
        if (patch.method !== undefined) next.identityMethod = patch.method;
        if (patch.weight !== undefined) next.identityWeight = patch.weight;
        if (patch.controlWeight !== undefined) {
          next.identityControlWeight = patch.controlWeight;
        }
        if (patch.noise !== undefined) next.identityNoise = patch.noise;
        if (patch.includeStyle !== undefined) {
          next.identityIncludeStyle = patch.includeStyle;
        }
        if (patch.image !== undefined) next.identityImage = patch.image;
        if (patch.engine && patch.engine !== "none" && !next.identityImage) {
          const fallback =
            referenceItems.find((item) => item.focus === "face") ?? referenceItems[0];
          next.identityImage = fallback?.id ?? null;
        }
        return next;
      });
    },
    [referenceItems],
  );

  const handleUpdateReference = useCallback(
    (
      assetId: string,
      patch: Partial<Pick<ReferenceItem, "focus" | "strength">>,
    ) => {
      setReferenceItems((current) =>
        current.map((item) => (item.id === assetId ? { ...item, ...patch } : item)),
      );
    },
    [],
  );

  const handleUploadReference = useCallback(
    async (file: File, replaceAssetId?: string) => {
      setReferenceUploading(true);
      setReferenceUploadError(null);
      try {
        const asset = await api.uploadReference(file);
        if (replaceAssetId) {
          setReferenceItems((current) =>
            current.map((item) =>
              item.id === replaceAssetId
                ? {
                    ...asset,
                    focus: item.focus,
                    strength: item.strength,
                  }
                : item,
            ),
          );
        } else {
          handleAddReference(asset);
        }
      } catch (cause) {
        setReferenceUploadError(
          cause instanceof Error ? cause.message : "참고 이미지 업로드에 실패했습니다.",
        );
      } finally {
        setReferenceUploading(false);
      }
    },
    [handleAddReference],
  );

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

  const handleSelectOutputDetails = useCallback(
    (item: OutputItem) => {
      handleSelectOutput(item);
      setDetailsJobId(item.job_id);
    },
    [handleSelectOutput],
  );

  const deleteResult = useCallback(
    async (kind: PageKind, jobId: string, promptText?: string) => {
      if (generating[kind]) return;
      const label = promptText?.trim()
        ? `"${promptText.trim().slice(0, 80)}" 결과`
        : "이 결과";
      const confirmed = window.confirm(
        `${label}를 삭제할까요?\n\n원본·후보·최종 이미지와 메타데이터가 모두 삭제되며 되돌릴 수 없습니다.`,
      );
      if (!confirmed) return;
      try {
        const response = await api.deleteOutput(jobId);
        setOutputsByPage((current) => ({
          ...current,
          [kind]: current[kind].filter((item) => item.job_id !== jobId),
        }));
        setJobHistory((current) => current.filter((job) => job.job_id !== jobId));
        setDisplays((current) =>
          current[kind]?.jobId === jobId ? { ...current, [kind]: null } : current,
        );
        setJobs((current) =>
          current[kind]?.job_id === jobId ? { ...current, [kind]: null } : current,
        );
        setJobIds((current) =>
          current[kind] === jobId ? { ...current, [kind]: null } : current,
        );
        setErrors((current) => ({ ...current, [kind]: null }));
        setNotices((current) => ({
          ...current,
          [kind]: response.message || "결과를 삭제했습니다.",
        }));
        void refreshJobHistory();
      } catch (cause) {
        setErrors((current) => ({
          ...current,
          [kind]: cause instanceof Error ? cause.message : "결과를 삭제하지 못했습니다.",
        }));
      }
    },
    [generating, refreshJobHistory],
  );

  const handleDeleteOutput = useCallback(
    (item: OutputItem) => {
      void deleteResult(item.kind ?? "pixel", item.job_id, item.prompt);
    },
    [deleteResult],
  );

  const handleDeleteCurrent = useCallback(() => {
    const display = displays[page];
    if (!display) return;
    void deleteResult(page, display.jobId, display.prompt);
  }, [deleteResult, displays, page]);

  const outputSizes = config?.output_sizes?.length ? config.output_sizes : DEFAULT_OUTPUT_SIZES;
  const imageSizes = config?.image_sizes?.length ? config.image_sizes : IMAGE_SIZES;
  const backendDown = Boolean(healthError) && !health;
  const comfyDown = health ? !health.comfyui.connected : backendDown;
  const connectionDetail =
    healthError ??
    health?.comfyui.error ??
    "ComfyUI가 시작 중이거나 연결이 끊겼습니다. 잠시 후 자동으로 다시 확인합니다.";
  const headerCheckpoint =
    page === "image"
      ? settings.imageCheckpoint
      : page === "reference"
        ? settings.referenceCheckpoint
        : settings.checkpoint;
  const headerLora =
    page === "image"
      ? (settings.imageLora ?? "")
      : page === "reference"
        ? (settings.referenceLora ?? "")
        : settings.lora;

  return (
    <div className="app-shell">
      <Header
        health={health}
        healthError={healthError}
        job={comicStudioOpen ? null : jobs[page]}
        checkpoint={headerCheckpoint}
        lora={headerLora}
      />

      <ResourceBar
        gpu={system?.gpu ?? health?.gpu ?? null}
        memory={system?.memory ?? health?.memory ?? null}
        queue={system?.queue ?? health?.queue ?? null}
        connected={Boolean(health?.comfyui.connected)}
      />

      <nav className="mode-tabs" aria-label="생성 모드">
        <button
          type="button"
          className={`mode-tab ${page === "pixel" && !comicStudioOpen ? "active" : ""}`}
          aria-pressed={page === "pixel" && !comicStudioOpen}
          onClick={() => {
            setPage("pixel");
            setComicStudioOpen(false);
          }}
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
          className={`mode-tab ${page === "image" && !comicStudioOpen ? "active" : ""}`}
          aria-pressed={page === "image" && !comicStudioOpen}
          onClick={() => {
            setPage("image");
            setComicStudioOpen(false);
          }}
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
        <button
          type="button"
          className={`mode-tab ${page === "reference" && !comicStudioOpen ? "active" : ""}`}
          aria-pressed={page === "reference" && !comicStudioOpen}
          onClick={() => {
            setPage("reference");
            setComicStudioOpen(false);
          }}
        >
          <span className="mode-tab-icon">
            <ImageIcon size={19} />
          </span>
          <span className="mode-tab-copy">
            <strong>이미지to이미지 느낌</strong>
            <small>참고 이미지 반영 · IP-Adapter Plus</small>
          </span>
          <span className="mode-tab-index">03</span>
        </button>
        <button
          type="button"
          className={`mode-tab ${comicStudioOpen ? "active" : ""}`}
          aria-pressed={comicStudioOpen}
          onClick={() => {
            setComicStudioOpen(true);
          }}
        >
          <span className="mode-tab-icon">
            <BookIcon size={19} />
          </span>
          <span className="mode-tab-copy">
            <strong>만화 스튜디오</strong>
            <small>콘티 · 후보 · 페이지 · 무검열 모델</small>
          </span>
          <span className="mode-tab-index">04</span>
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
            {backendDown && <BackendOverride />}
          </div>
        </div>
      )}

      {comicStudioOpen ? (
        <main className="workspace studio-workspace">
          <ComicStudioPanel models={health?.models.checkpoints ?? []} />
        </main>
      ) : (
      <main className="workspace">
        <div className="left-column">
          {page === "reference" && (
            <ReferencePanel
              items={referenceItems}
              samples={referenceSamples}
              capabilities={referenceCapabilities}
              samplesLoading={referenceSamplesLoading}
              capabilitiesLoading={referenceCapabilitiesLoading}
              capabilitiesError={referenceCapabilitiesError}
              checkpoint={settings.referenceCheckpoint}
              maxReferences={config?.reference_max_references ?? 5}
              busy={generating[page]}
              uploading={referenceUploading}
              uploadError={referenceUploadError}
              onAddAsset={handleAddReference}
              onUploadFile={(file, replaceId) => void handleUploadReference(file, replaceId)}
              onUpdateItem={handleUpdateReference}
              onRemoveItem={handleRemoveReference}
              onRefreshSamples={() => void loadReferenceSamples()}
              onRefreshCapabilities={() => void loadReferenceCapabilities()}
              identityEngine={settings.identityEngine}
              identityMethod={settings.identityMethod}
              identityWeight={settings.identityWeight}
              identityControlWeight={settings.identityControlWeight}
              identityNoise={settings.identityNoise}
              identityIncludeStyle={settings.identityIncludeStyle}
              identityImage={settings.identityImage}
              onIdentityChange={handleIdentityChange}
            />
          )}
          <PromptPanel
            kind={page}
            prompt={activePrompt}
            negativePrompt={activeNegative}
            onPromptChange={
              page === "image"
                ? setImagePrompt
                : page === "reference"
                  ? setReferencePrompt
                  : setPrompt
            }
            onNegativeChange={
              page === "image"
                ? setImageNegative
                : page === "reference"
                  ? setReferenceNegative
                  : setNegative
            }
            onResetNegative={handleResetNegative}
            onGenerate={() => void submit()}
            onCancel={() => void handleCancel()}
            busy={generating[page]}
            canGenerate={
              activePrompt.trim().length > 0 &&
              (page !== "reference" || referenceItems.length > 0)
            }
            autoTranslate={settings.autoTranslate}
            onAutoTranslateChange={(value) =>
              setSettings((current) => ({ ...current, autoTranslate: value }))
            }
            translation={isNativePage ? nativeTranslation : null}
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
          <JobList
            jobs={jobHistory}
            loading={jobHistoryLoading}
            activeJobId={jobIds[page]}
            onCancel={(jobId) => void handleCancelJob(jobId)}
            onSelect={handleSelectJob}
            onRefresh={() => void refreshJobHistory()}
          />
          {(page === "image" || page === "reference") && (
            <ModelPicker
              models={health?.models.checkpoints ?? []}
              selected={
                page === "reference"
                  ? (settings.referenceCheckpoint ?? null)
                  : (settings.imageCheckpoint ?? null)
              }
              onSelect={handleSelectModel}
              loading={!health}
            />
          )}
          {page === "reference" && (
            <ComicCuts
              buildPayload={(prompt) => buildPayload(prompt)}
              onFinished={() => void refreshOutputs("reference")}
              disabled={generating.reference || referenceItems.length === 0}
            />
          )}
          {(page === "reference" || page === "image") && (
            <ComicPagePanel kind={page} cuts={outputsByPage[page]} />
          )}
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
            detailsOpen={detailsJobId === displays[page]?.jobId}
            onRegenerate={handleRegenerate}
            onDelete={() => void handleDeleteCurrent()}
          />
          <Gallery
            kind={page}
            items={outputsByPage[page]}
            loading={outputsLoading}
            disabled={generating[page]}
            onSelect={handleSelectOutput}
            onSelectDetails={handleSelectOutputDetails}
            onDelete={handleDeleteOutput}
          />
        </div>
      </main>
      )}

      <footer className="app-footer">
        <span>PIXELFORGE LOCAL v{config?.app_version ?? "1.0.0"}</span>
        <span>100% LOCAL · COMFYUI + SDXL</span>
        <span>{config?.comfyui_url ?? "http://127.0.0.1:8188"}</span>
      </footer>
    </div>
  );
}
