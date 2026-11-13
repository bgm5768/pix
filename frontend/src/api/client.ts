import type {
  AppConfig,
  CancelResponse,
  ComicPageInfo,
  ComicStudioCharacter,
  ComicStudioCut,
  ComicStudioGenerateResult,
  ComicStudioPage,
  ComicStudioProject,
  ComicStudioProjectSummary,
  DeleteOutputResponse,
  GenerateRequest,
  GenerateResponse,
  HealthResponse,
  JobListResponse,
  JobView,
  ModelCatalogResponse,
  ModelDownloadItem,
  OutputsResponse,
  PageKind,
  ReferenceAsset,
  ReferenceCapabilities,
  ReferenceSamplesResponse,
  SystemStatusResponse,
  TranslateResponse,
} from "../types";

const ENV_API_BASE = ((import.meta.env.VITE_API_BASE as string | undefined) ?? "").replace(
  /\/+$/,
  "",
);
const API_BASE_KEY = "pixelforge.apiBase";

function normalizeApiBase(value: string): string {
  return value.trim().replace(/\/+$/, "");
}

/**
 * The backend origin can be baked in at build time (VITE_API_BASE) and then
 * overridden per browser, so the GitHub Pages UI can point at a LAN address or
 * a new tunnel URL without rebuilding the site.
 */
export function getApiBase(): string {
  try {
    const saved = normalizeApiBase(localStorage.getItem(API_BASE_KEY) ?? "");
    if (saved) return saved;
  } catch {
    // localStorage may be unavailable; fall back to the build-time value.
  }
  return ENV_API_BASE;
}

export function defaultApiBase(): string {
  return ENV_API_BASE;
}

export function setApiBase(value: string): void {
  const normalized = normalizeApiBase(value);
  try {
    if (normalized) {
      localStorage.setItem(API_BASE_KEY, normalized);
    } else {
      localStorage.removeItem(API_BASE_KEY);
    }
  } catch {
    // Ignore storage failures; the current page will still reload.
  }
}

export class ApiError extends Error {
  code?: string;
  status: number;
  extra?: string | null;

  constructor(message: string, status = 0, code?: string, extra?: string | null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.extra = extra;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${getApiBase()}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
      },
    });
  } catch {
    throw new ApiError(
      "諛깆뿏???쒕쾭???곌껐?????놁뒿?덈떎. start.bat???ㅽ뻾 以묒씤吏 ?뺤씤??二쇱꽭??",
      0,
      "BACKEND_UNREACHABLE",
    );
  }

  const text = await response.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = null;
    }
  }

  if (!response.ok) {
    const payload = (data ?? {}) as { detail?: unknown; code?: string; extra?: string | null };
    const detail =
      typeof payload.detail === "string"
        ? payload.detail
        : `?붿껌???ㅽ뙣?덉뒿?덈떎. (HTTP ${response.status})`;
    throw new ApiError(detail, response.status, payload.code, payload.extra ?? null);
  }
  return data as T;
}

export const api = {
  getConfig: () => request<AppConfig>("/api/config"),
  getHealth: () => request<HealthResponse>("/api/health"),
  getSystem: () => request<SystemStatusResponse>("/api/system"),
  getJobs: (limit = 20, kind?: PageKind) =>
    request<JobListResponse>(
      `/api/jobs?limit=${limit}${kind ? `&kind=${encodeURIComponent(kind)}` : ""}`,
    ),
  generate: (payload: GenerateRequest) =>
    request<GenerateResponse>("/api/generate", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getJob: (jobId: string) => request<JobView>(`/api/jobs/${encodeURIComponent(jobId)}`),
  cancelJob: (jobId: string) =>
    request<CancelResponse>(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, {
      method: "POST",
    }),
  getOutputs: (limit = 24, kind: PageKind = "pixel") =>
    request<OutputsResponse>(`/api/outputs?limit=${limit}&kind=${kind}`),
  deleteOutput: (jobId: string) =>
    request<DeleteOutputResponse>(`/api/outputs/${encodeURIComponent(jobId)}`, {
      method: "DELETE",
    }),
  translatePrompt: (text: string) =>
    request<TranslateResponse>("/api/translate", {
      method: "POST",
      body: JSON.stringify({ text }),
    }),
  getModelCatalog: () => request<ModelCatalogResponse>("/api/models/catalog"),
  startModelDownload: (downloadId: string) =>
    request<ModelDownloadItem>(`/api/models/downloads/${encodeURIComponent(downloadId)}`, {
      method: "POST",
    }),
  cancelModelDownload: (downloadId: string) =>
    request<ModelDownloadItem>(
      `/api/models/downloads/${encodeURIComponent(downloadId)}/cancel`,
      { method: "POST" },
    ),
  getReferenceSamples: () => request<ReferenceSamplesResponse>("/api/references/samples"),
  getReferenceCapabilities: (checkpoint?: string | null) =>
    request<ReferenceCapabilities>(
      checkpoint
        ? `/api/references/capabilities?checkpoint=${encodeURIComponent(checkpoint)}`
        : "/api/references/capabilities",
    ),
  getComicPages: () => request<{ items: ComicPageInfo[] }>("/api/comic/pages"),
  buildComicPage: (payload: {
    layout: string;
    width: number;
    height: number;
    title: string;
    panels: Array<{ path: string; text: string; position: string }>;
  }) =>
    request<ComicPageInfo>("/api/comic/page", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  deleteComicPage: (pageId: string) =>
    request<{ id: string; deleted: number }>(
      `/api/comic/page/${encodeURIComponent(pageId)}`,
      { method: "DELETE" },
    ),
  getComicStudioProjects: () =>
    request<{ items: ComicStudioProjectSummary[] }>("/api/comic-studio/projects"),
  createComicStudioProject: (payload: {
    title: string;
    model?: string;
    plan_yaml?: string;
  }) =>
    request<ComicStudioProject>("/api/comic-studio/projects", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getComicStudioProject: (projectId: string) =>
    request<ComicStudioProject>(
      `/api/comic-studio/projects/${encodeURIComponent(projectId)}`,
    ),
  updateComicStudioProject: (
    projectId: string,
    payload: { title?: string; model?: string; plan_yaml?: string },
  ) =>
    request<ComicStudioProject>(
      `/api/comic-studio/projects/${encodeURIComponent(projectId)}`,
      { method: "PUT", body: JSON.stringify(payload) },
    ),
  deleteComicStudioProject: (projectId: string) =>
    request<{ id: string; deleted: boolean }>(
      `/api/comic-studio/projects/${encodeURIComponent(projectId)}`,
      { method: "DELETE" },
    ),
  compileComicStudioProject: (projectId: string) =>
    request<{ id: string; cuts: number; pages: number; model: string; warnings: string[] }>(
      `/api/comic-studio/projects/${encodeURIComponent(projectId)}/compile`,
      { method: "POST" },
    ),
  generateComicStudioCut: (
    projectId: string,
    cutId: number,
    payload: {
      seeds?: string;
      count?: number;
      model?: string;
      steps?: number;
      cfg?: number;
      width?: number;
      height?: number;
      prompt_extra?: string;
      negative_extra?: string;
    },
  ) =>
    request<ComicStudioGenerateResult>(
      `/api/comic-studio/projects/${encodeURIComponent(projectId)}/cuts/${cutId}/generate`,
      { method: "POST", body: JSON.stringify(payload) },
    ),
  pickComicStudioCandidate: (
    projectId: string,
    cutId: number,
    candidate: string,
  ) =>
    request<ComicStudioCut>(
      `/api/comic-studio/projects/${encodeURIComponent(projectId)}/cuts/${cutId}/pick`,
      { method: "POST", body: JSON.stringify({ candidate }) },
    ),
  clearComicStudioPick: (projectId: string, cutId: number) =>
    request<ComicStudioCut>(
      `/api/comic-studio/projects/${encodeURIComponent(projectId)}/cuts/${cutId}/clear-pick`,
      { method: "POST" },
    ),
  deleteComicStudioCandidate: (
    projectId: string,
    cutId: number,
    candidate: string,
  ) =>
    request<ComicStudioCut>(
      `/api/comic-studio/projects/${encodeURIComponent(projectId)}/cuts/${cutId}/candidates/${encodeURIComponent(candidate)}`,
      { method: "DELETE" },
    ),
  buildComicStudioPage: (
    projectId: string,
    payload: {
      page: number;
      layout?: string;
      width?: number;
      height?: number;
      title?: string;
    },
  ) =>
    request<ComicStudioPage>(
      `/api/comic-studio/projects/${encodeURIComponent(projectId)}/pages`,
      { method: "POST", body: JSON.stringify(payload) },
    ),
  deleteComicStudioPage: (projectId: string, pageNumber: number) =>
    request<{ id: string; page: number; deleted: boolean }>(
      `/api/comic-studio/projects/${encodeURIComponent(projectId)}/pages/${pageNumber}`,
      { method: "DELETE" },
    ),
  getComicStudioCharacters: () =>
    request<{ items: ComicStudioCharacter[] }>("/api/comic-studio/characters"),
  saveComicStudioCharacter: (payload: {
    id: string;
    name: string;
    adult: boolean;
    gender: string;
    tags: string;
    default_outfit: string;
    negative: string;
    description: string;
  }) =>
    request<ComicStudioCharacter>("/api/comic-studio/characters", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  deleteComicStudioCharacter: (characterId: string) =>
    request<{ id: string; deleted: boolean }>(
      `/api/comic-studio/characters/${encodeURIComponent(characterId)}`,
      { method: "DELETE" },
    ),
  uploadReference: async (file: File): Promise<ReferenceAsset> => {    const form = new FormData();
    form.append("file", file, file.name);
    let response: Response;
    try {
      response = await fetch(`${getApiBase()}/api/references/upload`, {
        method: "POST",
        body: form,
      });
    } catch {
      throw new ApiError(
        "諛깆뿏???쒕쾭???곌껐?????놁뒿?덈떎. start.bat???ㅽ뻾 以묒씤吏 ?뺤씤??二쇱꽭??",
        0,
        "BACKEND_UNREACHABLE",
      );
    }
    const text = await response.text();
    let data: unknown = null;
    if (text) {
      try {
        data = JSON.parse(text);
      } catch {
        data = null;
      }
    }
    if (!response.ok) {
      const payload = (data ?? {}) as { detail?: unknown; code?: string; extra?: string | null };
      const detail =
        typeof payload.detail === "string"
          ? payload.detail
          : `?낅줈?쒖뿉 ?ㅽ뙣?덉뒿?덈떎. (HTTP ${response.status})`;
      throw new ApiError(detail, response.status, payload.code, payload.extra ?? null);
    }
    return data as ReferenceAsset;
  },
};

export function downloadUrl(jobId: string): string {
  return `${getApiBase()}/api/download/${encodeURIComponent(jobId)}`;
}

/**
 * Turn a backend-relative asset path ("/files/...", "/api/download/...") into
 * an absolute URL when the UI is hosted somewhere other than the backend
 * origin, such as GitHub Pages.
 */
export function assetUrl(path: string | null | undefined): string {
  if (!path) return "";
  if (/^(?:[a-z]+:)?\/\//i.test(path) || path.startsWith("data:") || path.startsWith("blob:")) {
    return path;
  }
  return `${getApiBase()}${path.startsWith("/") ? path : `/${path}`}`;
}

