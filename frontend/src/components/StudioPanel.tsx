import { useEffect, useMemo, useState } from "react";
import type {
  StudioDrawResult,
  StudioEpisode,
  StudioEpisodeDetail,
  StudioStatus,
} from "../types";
import { api, assetUrl } from "../api/client";
import {
  AlertIcon,
  CheckIcon,
  ImageIcon,
  InfoIcon,
  PlayIcon,
  RefreshIcon,
  SparkIcon,
} from "./Icons";

interface StudioPanelProps {
  status: StudioStatus | null;
  error: string | null;
  starting: boolean;
  refreshKey: number;
  onStart: () => void;
  onRefresh: () => void;
}

export function StudioPanel({
  status,
  error,
  starting,
  refreshKey,
  onStart,
  onRefresh,
}: StudioPanelProps) {
  const [frameLoaded, setFrameLoaded] = useState(false);
  const [flowsBusy, setFlowsBusy] = useState(false);
  const [flowsError, setFlowsError] = useState<string | null>(null);

  const [episodes, setEpisodes] = useState<StudioEpisode[]>([]);
  const [episodesError, setEpisodesError] = useState<string | null>(null);
  const [selectedEp, setSelectedEp] = useState("");
  const [detail, setDetail] = useState<StudioEpisodeDetail | null>(null);
  const [detailBusy, setDetailBusy] = useState(false);
  const [selectedCut, setSelectedCut] = useState("");
  const [selectedFlow, setSelectedFlow] = useState("");
  const [seedInput, setSeedInput] = useState("");
  const [copyToCandidates, setCopyToCandidates] = useState(true);
  const [drawBusy, setDrawBusy] = useState(false);
  const [drawError, setDrawError] = useState<string | null>(null);
  const [drawResult, setDrawResult] = useState<StudioDrawResult | null>(null);

  useEffect(() => {
    setFrameLoaded(false);
  }, [refreshKey]);

  const installed = status?.installed ?? false;
  const running = status?.running ?? false;
  const flows = useMemo(() => status?.flows ?? [], [status?.flows]);

  useEffect(() => {
    if (!running) {
      setEpisodes([]);
      setSelectedEp("");
      setDetail(null);
      return;
    }
    let cancelled = false;
    setEpisodesError(null);
    api
      .getStudioEpisodes()
      .then((items) => {
        if (cancelled) return;
        setEpisodes(items ?? []);
        setSelectedEp((current) => current || items[0]?.ep || "");
      })
      .catch((cause) => {
        if (cancelled) return;
        setEpisodesError(
          cause instanceof Error ? cause.message : "만화 목록을 불러오지 못했습니다.",
        );
      });
    return () => {
      cancelled = true;
    };
  }, [running, refreshKey]);

  useEffect(() => {
    if (!running || !selectedEp) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    setDetailBusy(true);
    setDrawResult(null);
    setDrawError(null);
    api
      .getStudioEpisode(selectedEp)
      .then((next) => {
        if (cancelled) return;
        setDetail(next);
        const solo = next.cuts.find((cut) => !cut.duo);
        setSelectedCut(String(solo?.id ?? next.cuts[0]?.id ?? ""));
      })
      .catch((cause) => {
        if (cancelled) return;
        setDetail(null);
        setEpisodesError(
          cause instanceof Error ? cause.message : "컷 목록을 불러오지 못했습니다.",
        );
      })
      .finally(() => {
        if (!cancelled) setDetailBusy(false);
      });
    return () => {
      cancelled = true;
    };
  }, [running, selectedEp, refreshKey]);

  useEffect(() => {
    if (!selectedFlow && flows.length > 0) {
      setSelectedFlow(flows[0].name);
    }
  }, [flows, selectedFlow]);

  const selectedCutInfo = detail?.cuts.find(
    (cut) => String(cut.id) === selectedCut,
  );
  const cutIsDuo = Boolean(
    selectedCutInfo?.duo ||
      (Array.isArray(selectedCutInfo?.roles) &&
        selectedCutInfo.roles.length > 0),
  );
  const canDraw =
    installed &&
    running &&
    Boolean(selectedEp) &&
    Boolean(selectedCut) &&
    Boolean(selectedFlow) &&
    !cutIsDuo &&
    !drawBusy;

  const refreshFlows = async () => {
    setFlowsBusy(true);
    setFlowsError(null);
    try {
      await api.refreshStudioFlows();
      onRefresh();
    } catch (cause) {
      setFlowsError(
        cause instanceof Error ? cause.message : "모델 목록을 갱신하지 못했습니다.",
      );
    } finally {
      setFlowsBusy(false);
    }
  };

  const drawCut = async () => {
    if (!canDraw) return;
    setDrawBusy(true);
    setDrawError(null);
    setDrawResult(null);
    try {
      const result = await api.drawStudioCut({
        ep: selectedEp,
        cut: Number(selectedCut),
        flow: selectedFlow,
        seeds: seedInput,
        copy_to_candidates: copyToCandidates,
      });
      setDrawResult(result);
      if (copyToCandidates) {
        const next = await api.getStudioEpisode(selectedEp).catch(() => null);
        if (next) setDetail(next);
      }
    } catch (cause) {
      setDrawError(
        cause instanceof Error ? cause.message : "선택한 모델로 그리지 못했습니다.",
      );
    } finally {
      setDrawBusy(false);
    }
  };

  return (
    <section className="panel studio-panel">
      <div className="panel-head">
        <div>
          <span className="eyebrow">04 · STUDIO</span>
          <h2>만화 작업실</h2>
        </div>
        <div className="studio-head-actions">
          <span
            className={`studio-state ${running ? "ok" : installed ? "idle" : "bad"}`}
          >
            {running ? (
              <>
                <CheckIcon size={12} /> 실행 중
              </>
            ) : installed ? (
              <>
                <SparkIcon size={12} /> 대기 중
              </>
            ) : (
              <>
                <AlertIcon size={12} /> nk 없음
              </>
            )}
          </span>
          {!running && installed && (
            <button
              type="button"
              className="btn btn-primary btn-small"
              onClick={onStart}
              disabled={starting}
            >
              {starting ? (
                <>
                  <span className="spinner" /> 시작 중...
                </>
              ) : (
                "작업실 켜기"
              )}
            </button>
          )}
          <button
            type="button"
            className="icon-button"
            onClick={onRefresh}
            title="상태 · 작업실 화면 새로고침"
          >
            <RefreshIcon size={14} />
          </button>
        </div>
      </div>

      <div className="studio-note">
        <InfoIcon size={14} />
        <span>
          nk 만화 제작기의 작업실(새 만화·이어서 만들기·컷 다시 그리기·페이지 조립)을
          그대로 불러옵니다. 같은 ComfyUI(<code>http://127.0.0.1:8188</code>)와 공유 모델
          폴더를 씁니다.
          <br />
          작업실은 이 PC의 파일을 만들고 명령을 실행하므로, 터널 주소를 아는 사람이 쓰게
          됩니다. 개인용 외에는 터널을 켜지 마세요.
        </span>
      </div>

      {error && (
        <div className="studio-error">
          <AlertIcon size={16} />
          <span>{error}</span>
        </div>
      )}

      {!installed && (
        <div className="studio-empty">
          <AlertIcon size={18} />
          <div>
            <strong>nk 만화 제작기를 찾지 못했습니다</strong>
            <p>
              설정 경로: <code>{status?.kit_path ?? "C:\\nk"}</code>
              <br />
              nk.py 가 있는 폴더를 <code>config/settings.yaml</code> 의
              <code> studio.kit_path</code> 에 지정해 주세요.
            </p>
          </div>
        </div>
      )}

      {installed && (
        <div className="studio-models">
          <div className="studio-models-head">
            <span className="field-label">그림 모델 (nk 워크플로)</span>
            <button
              type="button"
              className="text-button"
              onClick={() => void refreshFlows()}
              disabled={flowsBusy}
            >
              <RefreshIcon size={12} /> {flowsBusy ? "갱신 중..." : "모델 목록 갱신"}
            </button>
          </div>
          <p className="setting-note">
            설치된 SDXL 모델마다 nk 워크플로를 하나씩 만들어 둡니다. Anima 만화는
            작업실 안의 「그림 워크플로」가 숨겨져 있어서, 아래에서 모델을 골라 컷을
            그립니다.
          </p>
          {flowsError && <p className="reference-guidance is-warning">{flowsError}</p>}
          <div className="studio-model-list">
            {flows.map((flow) => (
              <button
                type="button"
                className={`studio-model-chip ${
                  selectedFlow === flow.name ? "is-selected" : ""
                }`}
                key={flow.name}
                title={flow.model}
                onClick={() => setSelectedFlow(flow.name)}
              >
                <strong>{flow.name}</strong>
                <small>
                  {flow.steps} steps · CFG {flow.cfg}
                </small>
              </button>
            ))}
            {flows.length === 0 && (
              <span className="setting-note">
                아직 워크플로가 없습니다. 「모델 목록 갱신」을 눌러 주세요.
              </span>
            )}
          </div>
        </div>
      )}

      {installed && (
        <div className="studio-draw">
          <div className="studio-draw-head">
            <span className="field-label">
              <ImageIcon size={13} /> 모델로 컷 그리기
            </span>
            <span className="setting-note">
              nk 의 캐릭터·장면·LoRA 규칙 그대로, 고른 모델로 다시 그립니다
            </span>
          </div>

          {episodesError && (
            <p className="reference-guidance is-warning">{episodesError}</p>
          )}

          <div className="studio-draw-grid">
            <label>
              <span>에피소드</span>
              <select
                value={selectedEp}
                onChange={(event) => setSelectedEp(event.target.value)}
                disabled={!running || episodes.length === 0 || drawBusy}
              >
                {episodes.map((episode) => (
                  <option value={episode.ep} key={episode.ep}>
                    {episode.ep} · {episode.title}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>컷</span>
              <select
                value={selectedCut}
                onChange={(event) => setSelectedCut(event.target.value)}
                disabled={!detail || drawBusy || detailBusy}
              >
                {(detail?.cuts ?? []).map((cut) => (
                  <option value={cut.id} key={cut.id}>
                    {cut.id}번 {cut.duo ? "· 두 명 컷" : ""}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>모델</span>
              <select
                value={selectedFlow}
                onChange={(event) => setSelectedFlow(event.target.value)}
                disabled={flows.length === 0 || drawBusy}
              >
                {flows.map((flow) => (
                  <option value={flow.name} key={flow.name}>
                    {flow.name} · {flow.steps} steps
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>시드</span>
              <input
                value={seedInput}
                onChange={(event) => setSeedInput(event.target.value)}
                placeholder="비우면 랜덤 (예: 123,456)"
                disabled={drawBusy}
              />
            </label>
          </div>

          {!running && (
            <p className="setting-note">
              작업실을 켜면 에피소드·컷 목록이 나옵니다.
            </p>
          )}

          <div className="studio-draw-actions">
            <label className="studio-check">
              <input
                type="checkbox"
                checked={copyToCandidates}
                onChange={(event) => setCopyToCandidates(event.target.checked)}
                disabled={drawBusy}
              />
              <span>nk 작업실 후보 목록에 추가</span>
            </label>
            <button
              type="button"
              className="btn btn-primary btn-small"
              onClick={() => void drawCut()}
              disabled={!canDraw}
            >
              {drawBusy ? (
                <>
                  <span className="spinner" /> 그리는 중...
                </>
              ) : (
                <>
                  <PlayIcon size={13} /> 이 모델로 그리기
                </>
              )}
            </button>
          </div>

          {cutIsDuo && (
            <p className="reference-guidance is-warning">
              두 명 컷은 nk 의 두 캐릭터 합성 경로가 필요해서 여기서는 아직 그릴 수
              없습니다. 컷을 하나만 고르거나, 작업실의 「다시 그리기」를 써 주세요.
            </p>
          )}
          {selectedCutInfo?.scene && (
            <p className="studio-draw-scene">
              <strong>{selectedCutInfo.id}번 컷</strong> {selectedCutInfo.scene}
            </p>
          )}
          {drawError && <p className="reference-guidance is-warning">{drawError}</p>}

          {drawResult && (
            <div className="studio-draw-result">
              <p>
                <strong>{drawResult.flow}</strong> · {drawResult.cut}번 컷 ·{" "}
                {drawResult.items.length}장
                {drawResult.items[0]?.copied
                  ? " · 작업실 후보에 추가됨"
                  : " · 미리보기만 만듦"}
              </p>
              <div className="studio-draw-thumbs">
                {drawResult.items.map((item) => (
                  <a
                    href={assetUrl(item.url)}
                    target="_blank"
                    rel="noreferrer"
                    key={item.path}
                  >
                    <img src={assetUrl(item.url)} alt={item.name} />
                    <span>
                      {item.name} · seed {item.seed}
                    </span>
                  </a>
                ))}
              </div>
              <p className="setting-note">
                {drawResult.items[0]?.copied
                  ? "작업실에서 해당 컷의 후보 목록을 열고 「이걸로」를 누르면 최종 컷이 됩니다. 화면이 안 바뀌면 위 새로고침을 눌러 주세요."
                  : "미리보기만 만들었습니다. 후보로 쓰려면 「nk 작업실 후보 목록에 추가」를 켜고 다시 그려 주세요."}
              </p>
              {drawResult.log && (
                <details className="studio-draw-log">
                  <summary>nk 출력 보기</summary>
                  <pre>{drawResult.log}</pre>
                </details>
              )}
            </div>
          )}
        </div>
      )}

      {installed && (
        <div className="studio-frame-wrap">
          <iframe
            key={refreshKey}
            className="studio-frame"
            title="nk 만화 작업실"
            src={assetUrl("/studio/")}
            onLoad={() => setFrameLoaded(true)}
          />
          {!frameLoaded && (
            <div className="studio-frame-loading">
              <span className="spinner" />
              작업실 화면을 불러오는 중...
            </div>
          )}
        </div>
      )}
    </section>
  );
}
