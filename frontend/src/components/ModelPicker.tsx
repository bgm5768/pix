import type { ModelFile } from "../types";
import { CheckIcon, SparkIcon } from "./Icons";

interface ModelPickerProps {
  models: ModelFile[];
  selected: string | null;
  onSelect: (model: ModelFile) => void;
  loading?: boolean;
}

function groupModels(models: ModelFile[]) {
  const usable = models.filter((model) => model.compatible && model.category !== "other");
  const manga = usable.filter((model) =>
    /애니|만화|일러스트|픽셀|furry/i.test(
      `${model.features.join(" ")} ${model.description} ${model.name}`,
    ),
  );
  const photo = usable.filter(
    (model) => !manga.includes(model) && /포토|실사|사진/i.test(model.features.join(" ")),
  );
  const rest = usable.filter((model) => !manga.includes(model) && !photo.includes(model));
  return [
    { id: "manga", label: "만화 · 애니", items: manga },
    { id: "photo", label: "포토리얼 · 실사", items: photo },
    { id: "general", label: "범용", items: rest },
  ].filter((group) => group.items.length > 0);
}

export function ModelPicker({
  models,
  selected,
  onSelect,
  loading = false,
}: ModelPickerProps) {
  const groups = groupModels(models);
  return (
    <section className="panel model-picker">
      <div className="panel-head">
        <div>
          <span className="eyebrow">MODEL</span>
          <h2>그림 모델 고르기</h2>
        </div>
        <span className="micro-badge">
          {models.filter((m) => m.compatible && m.category !== "other").length} SDXL 모델
        </span>
      </div>

      {loading && <p className="setting-note">모델 목록을 불러오는 중...</p>}

      {!loading && groups.length === 0 && (
        <p className="setting-note">
          사용할 수 있는 SDXL 체크포인트를 찾지 못했습니다. 설정 패널의 `모델 받기`에서
          모델을 받아 주세요.
        </p>
      )}

      {groups.map((group) => (
        <div className="model-group" key={group.id}>
          <span className="field-label">{group.label}</span>
          <div className="model-card-grid">
            {group.items.map((model) => {
              const active = model.name === selected;
              return (
                <button
                  key={model.name}
                  type="button"
                  className={`model-card ${active ? "is-active" : ""}`}
                  onClick={() => onSelect(model)}
                  title={model.description || model.name}
                >
                  <span className="model-card-top">
                    <strong>{model.name.replace(/\.safetensors$/i, "")}</strong>
                    {active && (
                      <span className="model-card-check">
                        <CheckIcon size={11} />
                      </span>
                    )}
                    {model.nsfw && <span className="model-card-nsfw">NSFW</span>}
                  </span>
                  <span className="model-card-desc">
                    {model.description || model.base_model || "SDXL 모델"}
                  </span>
                  <span className="model-card-tags">
                    {model.recommended_steps !== null && (
                      <span className="model-card-tag">
                        {model.recommended_steps} steps
                      </span>
                    )}
                    {model.recommended_cfg !== null && (
                      <span className="model-card-tag">CFG {model.recommended_cfg}</span>
                    )}
                    {model.base_model && (
                      <span className="model-card-tag">{model.base_model}</span>
                    )}
                    {/pony/i.test(model.name) && (
                      <span className="model-card-tag is-note">score 태그 자동</span>
                    )}
                  </span>
                  <span className="model-card-features">
                    {model.features.slice(0, 4).map((feature) => (
                      <span key={feature}>{feature}</span>
                    ))}
                  </span>
                  {!active && (
                    <span className="model-card-use">
                      <SparkIcon size={11} /> 이 모델 사용
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      ))}
    </section>
  );
}
