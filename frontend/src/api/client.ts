import type {
  AppConfig,
  CancelResponse,
  DeleteOutputResponse,
  GenerateRequest,
  GenerateResponse,
  HealthResponse,
  JobView,
  ModelCatalogResponse,
  ModelDownloadItem,
  OutputsResponse,
  PageKind,
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
      "백엔드 서버에 연결할 수 없습니다. start.bat이 실행 중인지 확인해 주세요.",
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
        : `요청이 실패했습니다. (HTTP ${response.status})`;
    throw new ApiError(detail, response.status, payload.code, payload.extra ?? null);
  }
  return data as T;
}

export const api = {
  getConfig: () => request<AppConfig>("/api/config"),
  getHealth: () => request<HealthResponse>("/api/health"),
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
