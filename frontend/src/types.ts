export type JobStatus =
  | "queued"
  | "preparing"
  | "generating"
  | "postprocessing"
  | "completed"
  | "error"
  | "cancelled";

export type PostProcessMode = "quantize" | "nearest" | "posterize";
export type OutputSize = 16 | 32 | 64 | 96 | 128;
export type AssetMode = "icon" | "character" | "object" | "tile";
export type ResizeFilter = "nearest" | "box" | "lanczos";
export type PageKind = "pixel" | "image";
export type ImageSize = 512 | 768 | 1024;
export type ModelCategory = "pixel" | "image" | "other";

export interface GenerateRequest {
  prompt: string;
  negative_prompt: string | null;
  mode: AssetMode;
  output_size: OutputSize;
  seed: number | null;
  steps: number;
  cfg: number;
  lora_strength: number;
  transparent: boolean;
  postprocess: PostProcessMode;
  palette_colors: number;
  resize_filter: ResizeFilter;
  candidates?: number;
  checkpoint?: string | null;
  lora?: string | null;
  kind: PageKind;
  image_size: ImageSize;
  translate_prompt?: boolean;
}

export interface QualityCheck {
  key: string;
  label: string;
  passed: boolean;
  value: string;
  message: string;
}

export interface PromptPlan {
  asset_type: string;
  subject: string;
  view: string;
  composition: string;
  style: string;
  background: string;
  detail_level: string;
  palette: string;
  output_resolution: number;
  mode: string;
  source: string;
  positive: string;
  negative: string;
}

export interface ResultInfo {
  original_url: string;
  cutout_url?: string | null;
  crop_url?: string | null;
  pixel_url?: string | null;
  preview_url: string;
  image_url?: string | null;
  image_preview_url?: string | null;
  download_url: string;
  width: number;
  height: number;
  preview_scale: number;
  palette_colors: number;
  transparent: boolean;
  postprocess: PostProcessMode;
  mode: AssetMode;
  kind: PageKind;
  subject_fill: number;
  resize_filter: ResizeFilter;
  quality: QualityCheck[];
  warnings: string[];
  candidates_generated: number;
  candidate_index: number;
  candidate_score: number;
  panel_suspected: boolean;
}

export interface JobView {
  job_id: string;
  status: JobStatus;
  stage_message: string;
  progress: number;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  request: GenerateRequest;
  seed_used: number | null;
  base_seed: number | null;
  prompt_original: string | null;
  prompt_used: string | null;
  prompt_translated: boolean;
  negative_used: string | null;
  comfy_prompt_id: string | null;
  step: number;
  total_steps: number;
  queue_position: number;
  prompt_plan: PromptPlan | null;
  result: ResultInfo | null;
  error: string | null;
  error_code: string | null;
}

export interface GenerateResponse {
  job_id: string;
  status: JobStatus;
  queue_position: number;
}

export interface CancelResponse {
  job_id: string;
  status: JobStatus;
  message: string;
}

export interface TranslateResponse {
  source: string;
  text: string;
  translated: boolean;
  model: string;
  elapsed_ms: number;
  error: string | null;
}

export interface TranslationPreview {
  source: string;
  text: string;
  status: "idle" | "loading" | "done" | "error";
  translated: boolean;
  error: string | null;
}

export interface DeleteOutputResponse {
  job_id: string;
  deleted: string[];
  count: number;
  message: string;
}

export interface ModelAvailability {
  name: string;
  available: boolean;
}

export interface ModelFile {
  name: string;
  size_bytes: number;
  compatible: boolean;
  category: ModelCategory;
  description: string;
  features: string[];
  trigger: string | null;
  prompt_tip: string | null;
  recommended_strength: number | null;
  recommended_steps: number | null;
  recommended_cfg: number | null;
  base_model: string;
  nsfw: boolean;
  vram_hint: string;
}

export interface ModelDownloadItem {
  id: string;
  label: string;
  kind: "checkpoint" | "lora";
  filename: string;
  description: string;
  features: string[];
  trigger: string | null;
  prompt_tip: string | null;
  recommended_strength: number | null;
  recommended_steps: number | null;
  recommended_cfg: number | null;
  base_model: string;
  nsfw: boolean;
  vram_hint: string;
  size_bytes: number;
  status: "not_installed" | "downloading" | "installed" | "error" | "cancelled";
  progress: number;
  downloaded_bytes: number;
  speed_bps: number;
  error: string | null;
}

export interface ModelCatalogResponse {
  items: ModelDownloadItem[];
  models_dir: string;
}

export interface GpuStatus {
  name: string;
  vram_total: number;
  vram_free: number;
  vram_used: number;
  utilization: number | null;
  temperature_c: number | null;
  power_w: number | null;
  power_limit_w: number | null;
  source: "nvidia-smi" | "comfyui";
  state: string;
}

export interface MemoryStatus {
  total: number;
  used: number;
  available: number;
  percent: number;
}

export interface QueueStatus {
  active: number;
  pending: number;
}

export interface HealthResponse {
  status: string;
  app_version: string;
  comfyui: {
    connected: boolean;
    url: string;
    version: string | null;
    error: string | null;
  };
  gpu: GpuStatus | null;
  memory: MemoryStatus | null;
  models: {
    checkpoint: ModelAvailability;
    lora: ModelAvailability;
    checkpoints: ModelFile[];
    loras: ModelFile[];
  };
  queue: QueueStatus;
  timestamp: string;
}

export interface SystemStatusResponse {
  gpu: GpuStatus | null;
  memory: MemoryStatus | null;
  queue: QueueStatus;
  timestamp: string;
}

export interface JobListResponse {
  items: JobView[];
  active: number;
  pending: number;
}

export interface OutputItem {
  job_id: string;
  pixel_url?: string | null;
  image_url?: string | null;
  preview_url: string;
  original_url: string;
  cutout_url?: string | null;
  crop_url?: string | null;
  download_url: string;
  width: number;
  height: number;
  created_at: string;
  prompt: string;
  seed: number | null;
  transparent: boolean;
  postprocess: PostProcessMode;
  mode: AssetMode;
  kind: PageKind;
  output_size: number;
  palette_colors: number;
  subject_fill: number;
  resize_filter: ResizeFilter;
  quality: QualityCheck[];
  candidates_generated: number;
  candidate_index: number;
  candidate_score: number;
  panel_suspected: boolean;
}

export interface OutputsResponse {
  items: OutputItem[];
  total: number;
}

export interface AppConfig {
  app_name: string;
  app_version: string;
  comfyui_url: string;
  checkpoint: string;
  lora: string;
  output_sizes: OutputSize[];
  default_output_size: OutputSize;
  default_steps: number;
  default_cfg: number;
  default_lora_strength: number;
  default_transparent: boolean;
  default_postprocess: PostProcessMode;
  default_palette_colors: number;
  default_resize_filter: ResizeFilter;
  default_candidates: number;
  max_candidates: number;
  candidate_options: number[];
  palette_options: number[];
  default_image_size: ImageSize;
  image_sizes: ImageSize[];
  image_checkpoint: string;
  image_lora: string;
  default_image_candidates: number;
  default_image_negative_prompt: string;
  default_negative_prompt: string;
  translation_enabled?: boolean;
  translation_model?: string;
  max_pending: number;
}

export interface AppSettings {
  mode: AssetMode;
  outputSize: OutputSize;
  seedInput: string;
  steps: number;
  cfg: number;
  loraStrength: number;
  transparent: boolean;
  postprocess: PostProcessMode;
  paletteColors: number;
  resizeFilter: ResizeFilter;
  checkpoint: string | null;
  lora: string | null;
  imageSize: ImageSize;
  imageCheckpoint: string | null;
  imageLora: string | null;
  autoTranslate: boolean;
}

export interface DisplayResult {
  jobId: string;
  result: ResultInfo;
  prompt?: string;
  seed?: number | null;
  createdAt?: string;
  live?: boolean;
  promptPlan?: PromptPlan | null;
}
