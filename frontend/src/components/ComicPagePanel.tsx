import { useEffect, useState } from "react";
import type { OutputItem, PageKind } from "../types";
import { api, assetUrl } from "../api/client";
import { AlertIcon, CheckIcon, DownloadIcon, SparkIcon } from "./Icons";

interface ComicPagePanelProps {
  kind: PageKind;
  cuts: OutputItem[];
}

interface PageInfo {
  id: string;
  image_url: string;
  pdf_url: string;
  layout: string;
  width: number;
  height: number;
  title: string;
  panel_count: number;
}

const LAYOUTS = [
  { id: "2x2", label: "2×2 (4컷)" },
  { id: "1x2", label: "1×2 (2컷 가로)" },
  { id: "2x1", label: "2×1 (2컷 세로)" },
  { id: "1x3", label: "1×3 (3컷 가로)" },
  { id: "3x1", label: "3×1 (3컷 세로)" },
  { id: "2x3", label: "2×3 (6컷)" },
  { id: "1x1", label: "1×1 (큰 컷)" },
];

interface Selected {
  url: string;
  label: string;
  text: string;
  position: "top" | "bottom" | "none";
}

function layoutCapacity(layout: string): number {
  const [rows, cols] = layout.split("x").map((part) => Number(part) || 1);
  return rows * cols;
}

export function ComicPagePanel({ kind, cuts }: ComicPagePanelProps) {
  const [layout, setLayout] = useState("2x2");
  const [title, setTitle] = useState("");
  const [selected, setSelected] = useState<Selected[]>([]);
  const [page, setPage] = useState<PageInfo | null>(null);
  const [pages, setPages] = useState<PageInfo[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const capacity = layoutCapacity(layout);

  const loadPages = async () => {
    try {
      const response = await api.getComicPages();
      setPages(response.items);
    } catch {
      // The list is a convenience; ignore transient failures.
    }
  };

  useEffect(() => {
    void loadPages();
  }, []);

  const toggleCut = (item: OutputItem) => {
    setPage(null);
    setSelected((current) => {
      if (current.some((entry) => entry.url === item.image_url)) {
        return current.filter((entry) => entry.url !== item.image_url);
      }
      if (current.length >= capacity) return current;
      return [
        ...current,
        {
          url: item.image_url ?? item.preview_url,
          label: item.prompt || item.job_id,
          text: "",
          position: "top",
        },
      ];
    });
  };

  const build = async () => {
    if (selected.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api.buildComicPage({
        layout,
        width: 1240,
        height: 1754,
        title,
        panels: selected.map((entry) => ({
          path: entry.url,
          text: entry.text,
          position: entry.position,
        })),
      });
      setPage(result);
      await loadPages();
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "페이지를 만들지 못했습니다.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="panel comic-page-panel">
      <div className="panel-head">
        <div>
          <span className="eyebrow">PAGE</span>
          <h2>만화 페이지 조립</h2>
        </div>
        <span className="micro-badge">{selected.length}/{capacity} CUTS</span>
      </div>

      <p className="setting-note">
        고른 컷을 한 쪽에 배치하고 말풍선을 넣어 PNG·PDF로 저장합니다. 컷은 위쪽 갤러리
        ({kind === "reference" ? "레퍼런스" : "이미지"} 페이지)에서 골라 주세요.
      </p>

      <div className="comic-page-controls">
        <label className="reference-control">
          <span>레이아웃</span>
          <select
            className="select-input select-small"
            value={layout}
            onChange={(event) => {
              setLayout(event.target.value);
              setSelected((current) =>
                current.slice(0, layoutCapacity(event.target.value)),
              );
            }}
          >
            {LAYOUTS.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        <label className="reference-control">
          <span>페이지 제목</span>
          <input
            className="text-input"
            value={title}
            placeholder="예: 1화 - 첫 만남"
            onChange={(event) => setTitle(event.target.value)}
          />
        </label>
      </div>

      <div className="comic-cut-picker">
        {cuts.length === 0 && (
          <p className="setting-note">고를 컷이 없습니다. 먼저 컷을 만들어 주세요.</p>
        )}
        {cuts.map((item) => {
          const url = item.image_url ?? item.preview_url;
          const active = selected.some((entry) => entry.url === url);
          return (
            <button
              key={item.job_id}
              type="button"
              className={`comic-cut-pick ${active ? "is-active" : ""}`}
              onClick={() => toggleCut(item)}
              title={item.prompt || item.job_id}
            >
              <img src={assetUrl(url)} alt={item.prompt || item.job_id} />
              {active && (
                <span className="comic-cut-pick-check">
                  <CheckIcon size={11} />
                </span>
              )}
            </button>
          );
        })}
      </div>

      {selected.length > 0 && (
        <div className="comic-dialogues">
          {selected.map((entry, index) => (
            <div className="comic-dialogue" key={`${entry.url}-${index}`}>
              <span className="comic-dialogue-index">{index + 1}</span>
              <input
                className="text-input"
                value={entry.text}
                placeholder="이 컷의 대사"
                onChange={(event) => {
                  const value = event.target.value;
                  setSelected((current) =>
                    current.map((item, i) =>
                      i === index ? { ...item, text: value } : item,
                    ),
                  );
                }}
              />
              <select
                className="select-input select-small"
                value={entry.position}
                onChange={(event) => {
                  const value = event.target.value as Selected["position"];
                  setSelected((current) =>
                    current.map((item, i) =>
                      i === index ? { ...item, position: value } : item,
                    ),
                  );
                }}
              >
                <option value="top">위</option>
                <option value="bottom">아래</option>
                <option value="none">없음</option>
              </select>
            </div>
          ))}
        </div>
      )}

      {error && (
        <div className="studio-error">
          <AlertIcon size={16} />
          <span>{error}</span>
        </div>
      )}

      <div className="comic-page-actions">
        <button
          type="button"
          className="btn btn-primary btn-small"
          onClick={() => void build()}
          disabled={busy || selected.length === 0}
        >
          {busy ? (
            <>
              <span className="spinner" /> 페이지 만드는 중...
            </>
          ) : (
            <>
              <SparkIcon size={14} /> 페이지 만들기
            </>
          )}
        </button>
        {page && (
          <>
            <a className="btn btn-ghost btn-small" href={assetUrl(page.image_url)} download>
              <DownloadIcon size={13} /> PNG
            </a>
            <a className="btn btn-ghost btn-small" href={assetUrl(page.pdf_url)} download>
              <DownloadIcon size={13} /> PDF
            </a>
          </>
        )}
      </div>

      {page && (
        <div className="comic-page-preview">
          <img src={assetUrl(page.image_url)} alt="조립한 만화 페이지" />
        </div>
      )}

      {pages.length > 0 && (
        <div className="comic-page-history">
          <span className="field-label">만든 페이지</span>
          <div className="comic-page-history-grid">
            {pages.slice(0, 6).map((item) => (
              <a
                key={item.id}
                className="comic-page-history-item"
                href={assetUrl(item.image_url)}
                target="_blank"
                rel="noreferrer"
                title={item.title || item.id}
              >
                <img src={assetUrl(item.image_url)} alt={item.title || item.id} />
                <span>
                  {item.title || "(제목 없음)"} · {item.panel_count}컷
                </span>
              </a>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
