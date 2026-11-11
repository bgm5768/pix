import type { OutputItem, PageKind } from "../types";
import { assetUrl } from "../api/client";
import { formatRelative } from "../utils";
import { DownloadIcon, InfoIcon, TrashIcon } from "./Icons";

interface GalleryProps {
  kind: PageKind;
  items: OutputItem[];
  loading: boolean;
  disabled: boolean;
  onSelect: (item: OutputItem) => void;
  onSelectDetails: (item: OutputItem) => void;
  onDelete: (item: OutputItem) => void;
}

export function Gallery({
  kind,
  items,
  loading,
  disabled,
  onSelect,
  onSelectDetails,
  onDelete,
}: GalleryProps) {
  const isImage = kind === "image";
  const isReference = kind === "reference";
  const isNative = isImage || isReference;
  return (
    <section className="panel gallery-panel">
      <div className="panel-head">
        <div>
          <span className="eyebrow">05 · ARCHIVE</span>
          <h2>
            {isReference
              ? "최근 레퍼런스 결과"
              : isImage
                ? "최근 이미지"
                : "최근 결과"}
          </h2>
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
          {isReference
            ? "아직 저장된 레퍼런스 결과가 없습니다. 첫 레퍼런스 이미지를 만들어 보세요."
            : isImage
              ? "아직 저장된 이미지가 없습니다. 첫 이미지를 만들어 보세요."
              : "아직 저장된 결과가 없습니다. 첫 도트를 만들어 보세요."}
        </p>
      ) : (
        <div className="gallery-grid">
          {items.map((item) => {
            const src = isNative ? (item.image_url ?? item.preview_url) : item.preview_url;
            const filename = `pixelforge_${item.job_id}_${
              isImage ? "image_" : isReference ? "reference_" : ""
            }${item.output_size}px.png`;
            return (
              <article key={item.job_id} className="gallery-card">
                <button
                  type="button"
                  className="gallery-open"
                  onClick={() => onSelect(item)}
                  disabled={disabled}
                  title={item.prompt || `${item.output_size}px ${isNative ? "이미지" : "도트"}`}
                >
                  <div className={`gallery-thumb ${isNative ? "image-thumb" : "checker"}`}>
                    <img
                      src={assetUrl(src)}
                      alt={`${item.output_size}px ${isNative ? "이미지" : "도트"} 썸네일`}
                      style={isNative ? undefined : { imageRendering: "pixelated" }}
                      loading="lazy"
                    />
                    {!isNative && item.transparent && <span className="thumb-alpha">α</span>}
                    {isReference && item.references && item.references.length > 0 && (
                      <span className="thumb-refs">REF {item.references.length}</span>
                    )}
                  </div>
                  <div className="gallery-meta">
                    <span className="gallery-size">
                      {isReference
                        ? `${item.output_size}px REF`
                        : isImage
                          ? `${item.output_size}px IMAGE`
                          : `${item.output_size}px`}
                    </span>
                    <span>{formatRelative(item.created_at)}</span>
                  </div>
                  <p>{item.prompt || "프롬프트 기록 없음"}</p>
                </button>
                <div className="gallery-actions">
                  <button
                    type="button"
                    className="gallery-action"
                    onClick={(event) => {
                      event.stopPropagation();
                      onSelectDetails(item);
                    }}
                    disabled={disabled}
                    title="이 결과를 만든 프롬프트·모델·설정 보기"
                    aria-label="생성 정보 보기"
                  >
                    <InfoIcon size={13} />
                  </button>
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
