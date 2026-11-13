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
export type PageKind = "pixel" | "image" | "reference";
export type ImageSize = 512 | 768 | 1024;
export type ModelCategory = "pixel" | "image" | "other";
export type ReferenceFocus = "appearance" | "face" | "style" | "pose" | "composition";
export type IdentityEngine = "none" | "instantid" | "pulid";
export type IdentityMethod = "fidelity" | "style" | "neutral";

export interface ReferenceInput {
  asset_id: string;
  strength: number;
  focus: ReferenceFocus;
}

export interface ReferenceAnalysis {
  width: number;
  height: number;
  orientation: "portrait" | "landscape" | "square";
  brightness: number;
  saturation: number;
  colorfulness: number;
  dominant_colors: string[];
  subject_hint: string;
  summary: string;
}

export interface ReferenceAsset {
  id: string;
  name: string;
  url: string;
  source: "upload" | "sample";
  width: number;
  height: number;
  size_bytes: number;
  hint: string;
  analysis: ReferenceAnalysis;
}

export interface ReferenceUsage {
  asset_id: string;
  name: string;
  url: string;
  focus: ReferenceFocus;
  strength: number;
  analysis_summary: string;
}

export interface IdentityUsage {
  engine: IdentityEngine;
  image: string | null;
  name: string;
  url: string;
  weight: number;
  method: IdentityMethod;
  control_weight?: number;
  noise?: number;
  include_style?: boolean;
}

export interface GenerationDetails {
  prompt: string;
  prompt_used: string;
  negative_prompt: string;
  prompt_translated: boolean;
  checkpoint: string;
  lora: string;
  lora_enabled: boolean;
  steps: number;
  cfg: number;
  lora_strength: number;
  sampler: string;
  scheduler: string;
  width: number;
  height: number;
  seed: number | null;
  mode: string;
  postprocess: string;
  transparent: boolean;
  palette_colors: number;
  elapsed_seconds: number;
  created_at: string;
  references?: ReferenceUsage[];
  identity?: IdentityUsage | null;
}

export interface ReferenceItem extends ReferenceAsset {
  focus: ReferenceFocus;
  strength: number;
}

export interface ReferenceCapabilities {
  available: boolean;
  node_installed: boolean;
  advanced_node_installed: boolean;
  plus_model: boolean;
  plus_face_model: boolean;
  clip_vision_model: boolean;
  ipadapter_models: string[];
  clip_vision_models: string[];
  checkpoint: string | null;
  checkpoint_compatible: boolean | null;
  checkpoint_note: string;
  guidance: string;
  install_hint: string;
  instantid_note: string;
  pulid_note: string;
  max_references: number;
  presets: string[];
  instantid_available: boolean;
  instantid_node_installed: boolean;
  instantid_model: boolean;
  instantid_controlnet: boolean;
  instantid_models: string[];
  pulid_available: boolean;
  pulid_node_installed: boolean;
  pulid_model: boolean;
  pulid_models: string[];
  insightface_available: boolean;
  insightface_models: string[];
  identity_engines: string[];
  identity_guidance: string;
}

export interface ReferenceSamplesResponse {
  items: ReferenceAsset[];
}

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
  image_width?: number | null;
  image_height?: number | null;
  translate_prompt?: boolean;
  reference_images?: ReferenceInput[];
  identity_engine?: IdentityEngine;
  identity_image?: string | null;
  identity_weight?: number;
  identity_method?: IdentityMethod;
  identity_control_weight?: number;
  identity_noise?: number;
  identity_include_style?: boolean;
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
  references?: ReferenceUsage[];
  identity?: IdentityUsage | null;
  details?: GenerationDetails | null;
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
  references?: ReferenceUsage[];
  identity?: IdentityUsage | null;
  details?: GenerationDetails | null;
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
  reference_checkpoint: string;
  reference_lora: string;
  reference_default_size: ImageSize;
  reference_default_strength: number;
  reference_default_focus: ReferenceFocus;
  reference_max_references: number;
  default_negative_prompt: string;
  translation_enabled?: boolean;
  translation_model?: string;
  max_pending: number;
}

export interface ComicPageInfo {
  id: string;
  created_at?: string;
  layout: string;
  width: number;
  height: number;
  title: string;
  panel_count: number;
  image_url: string;
  pdf_url: string;
}

export interface StudioFlow {
  name: string;
  model: string;
  steps: number;
  cfg: number;
}

export interface StudioStatus {
  installed: boolean;
  kit_path: string;
  running: boolean;
  port: number;
  url: string;
  python: string;
  allowed?: boolean;
  remote_blocked?: boolean;
  policy_agreed?: boolean;
  flows?: StudioFlow[];
}

export interface StudioEpisode {
  ep: string;
  title: string;
  pages: number;
  test?: boolean;
  mtime?: number;
}

export interface StudioCut {
  id: number;
  page?: number;
  shot?: string;
  scene?: string;
  duo?: boolean;
  roles?: unknown;
  img?: string;
  cands?: { name: string; img: string }[];
}

export interface StudioEpisodeDetail {
  ep: string;
  title?: string;
  anima?: boolean;
  flow?: string | null;
  flows?: string[];
  cuts: StudioCut[];
  has_plan?: boolean;
  has_conti?: boolean;
  error?: string | null;
}

export interface StudioDrawItem {
  name: string;
  seed: number;
  source: string;
  path: string;
  url: string;
  copied: boolean;
}

export interface StudioDrawResult {
  ep: string;
  cut: number;
  flow: string;
  items: StudioDrawItem[];
  output_dir: string;
  log: string;
}

export interface ComicStudioCharacter {
  id: string;
  name: string;
  adult: boolean;
  gender: string;
  tags: string;
  default_outfit: string;
  negative: string;
  description: string;
  builtin?: boolean;
}

export interface ComicStudioCandidate {
  name: string;
  url: string;
  seed: number;
  model: string;
  width: number;
  height: number;
  created_at: string;
  elapsed?: number;
  steps?: number;
  cfg?: number;
  prompt?: string;
}

export interface ComicStudioCut {
  id: number;
  key: string;
  page: number;
  index: number;
  shot: string;
  angle: string;
  loc: string;
  who: string[];
  characters: string[];
  action: string;
  scene: string;
  text: string;
  position: "top" | "bottom" | "none";
  width: number;
  height: number;
  prompt: string;
  negative: string;
  steps: number;
  cfg: number;
  candidates: ComicStudioCandidate[];
  selected: string | null;
  selected_url: string | null;
}

export interface ComicStudioPlanPage {
  number: number;
  note: string;
  cut_ids: number[];
}

export interface ComicStudioPage {
  id: string;
  number: number;
  note?: string;
  layout: string;
  width: number;
  height: number;
  title: string;
  panel_count: number;
  image_url: string;
  pdf_url: string;
  created_at?: string;
}

export interface ComicStudioProjectSummary {
  id: string;
  title: string;
  model: string;
  cut_count: number;
  candidate_count: number;
  picked_count: number;
  page_count: number;
  updated_at: string;
  cover_url: string | null;
  error: string | null;
}

export interface ComicStudioProject {
  id: string;
  title: string;
  model: string;
  plan_yaml: string;
  created_at: string;
  updated_at: string;
  cuts: ComicStudioCut[];
  pages: ComicStudioPage[];
  plan_pages: ComicStudioPlanPage[];
  warnings: string[];
  error: string | null;
  compiled: {
    title: string;
    style: string;
    negative: string;
    rating: string;
    page_count: number;
    cut_count: number;
  };
  characters: ComicStudioCharacter[];
}

export interface ComicStudioGenerateResult {
  project_id: string;
  cut: ComicStudioCut;
  generated: ComicStudioCandidate[];
  model: string;
  log: string;
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
  // Explicit output size for comic panels (null = square, imageSize x imageSize).
  imageWidth: number | null;
  imageHeight: number | null;
  referenceSize: ImageSize;
  referenceCheckpoint: string | null;
  referenceLora: string | null;
  referenceStrength: number;
  referenceFocus: ReferenceFocus;
  identityEngine: IdentityEngine;
  identityMethod: IdentityMethod;
  identityWeight: number;
  identityControlWeight: number;
  identityNoise: number;
  identityIncludeStyle: boolean;
  identityImage: string | null;
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
