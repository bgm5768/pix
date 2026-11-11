import type {
  AppConfig,
  CancelResponse,
  GenerateRequest,
  GenerateResponse,
  HealthResponse,
  JobView,
  ModelCatalogResponse,
  ModelDownloadItem,
  OutputsResponse,
  PageKind,
} from "../types";

const API_BASE = ((import.meta.env.VITE_API_BASE as string | undefined) ?? "").replace(
  /\/+$/,
  "",
);

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
    response = await fetch(`${API_BASE}${path}`, {
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
  return `${API_BASE}/api/download/${encodeURIComponent(jobId)}`;
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
  return `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
}
