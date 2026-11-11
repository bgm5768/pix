import type { OutputItem, PageKind } from "../types";
import { assetUrl } from "../api/client";
import { formatRelative } from "../utils";
import { DownloadIcon, TrashIcon } from "./Icons";

interface GalleryProps {
  kind: PageKind;
  items: OutputItem[];
  loading: boolean;
  disabled: boolean;
  onSelect: (item: OutputItem) => void;
  onDelete: (item: OutputItem) => void;
}

export function Gallery({ kind, items, loading, disabled, onSelect, onDelete }: GalleryProps) {
  const isImage = kind === "image";
  return (
    <section className="panel gallery-panel">
      <div className="panel-head">
        <div>
          <span className="eyebrow">05 · ARCHIVE</span>
          <h2>{isImage ? "최근 이미지" : "최근 결과"}</h2>
        </div>
        <span className="micro-badge">{items.length} SAVED</span>
      </div>

      {loading && items.length === 0 ? (
        <div className="gallery-grid">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="gallery-skeleton" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <p className="gallery-empty">
          {isImage
            ? "아직 저장된 이미지가 없습니다. 첫 이미지를 만들어 보세요."
            : "아직 저장된 결과가 없습니다. 첫 도트를 만들어 보세요."}
        </p>
      ) : (
        <div className="gallery-grid">
          {items.map((item) => {
            const src = isImage ? (item.image_url ?? item.preview_url) : item.preview_url;
            const filename = `pixelforge_${item.job_id}_${isImage ? "image_" : ""}${item.output_size}px.png`;
            return (
              <article key={item.job_id} className="gallery-card">
                <button
                  type="button"
                  className="gallery-open"
                  onClick={() => onSelect(item)}
                  disabled={disabled}
                  title={item.prompt || `${item.output_size}px ${isImage ? "이미지" : "도트"}`}
                >
                  <div className={`gallery-thumb ${isImage ? "image-thumb" : "checker"}`}>
                    <img
                      src={assetUrl(src)}
                      alt={`${item.output_size}px ${isImage ? "이미지" : "도트"} 썸네일`}
                      style={isImage ? undefined : { imageRendering: "pixelated" }}
                      loading="lazy"
                    />
                    {!isImage && item.transparent && <span className="thumb-alpha">α</span>}
                  </div>
                  <div className="gallery-meta">
                    <span className="gallery-size">
                      {isImage ? `${item.output_size}px IMAGE` : `${item.output_size}px`}
                    </span>
                    <span>{formatRelative(item.created_at)}</span>
                  </div>
                  <p>{item.prompt || "프롬프트 기록 없음"}</p>
                </button>
                <div className="gallery-actions">
                  <a
                    className="gallery-action"
                    href={assetUrl(item.download_url)}
                    download={filename}
                    title="PNG 다운로드"
                    aria-label="PNG 다운로드"
                    onClick={(event) => event.stopPropagation()}
                  >
                    <DownloadIcon size={13} />
                  </a>
                  <button
                    type="button"
                    className="gallery-action danger"
                    onClick={(event) => {
                      event.stopPropagation();
                      onDelete(item);
                    }}
                    disabled={disabled}
                    title="결과 삭제"
                    aria-label="결과 삭제"
                  >
                    <TrashIcon size={13} />
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
