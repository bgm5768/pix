import { useEffect, useState } from "react";
import type { StudioStatus } from "../types";
import { api, assetUrl } from "../api/client";
import { AlertIcon, CheckIcon, InfoIcon, RefreshIcon, SparkIcon } from "./Icons";

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
  useEffect(() => {
    setFrameLoaded(false);
  }, [refreshKey]);

  const installed = status?.installed ?? false;
  const running = status?.running ?? false;
  const flows = status?.flows ?? [];

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
            title="상태 새로고침"
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
          폴더를 쓰고, nk 의 안전장치(전연령 전용)도 그대로 적용됩니다.
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

      {installed && status?.policy_agreed === false && (
        <div className="studio-warn">
          <AlertIcon size={16} />
          <span>
            nk 작업실이 사용 정책 동의를 기다리고 있습니다(<code>.nk_agreed</code> 없음).
            콘솔에서 <code>{"cd C:\\nk && python nk.py list"}</code> 를 한 번 실행하고{" "}
            <code>agree</code> 를 입력하면 작업실 작업이 다시 동작합니다.
          </span>
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
            설치된 SDXL 모델마다 nk 워크플로를 하나씩 만들어 둡니다. 작업실 안의
            <strong> 「그림 워크플로」</strong> 드롭다운에서 모델을 고르면 그 모델로 그려집니다.
          </p>
          {flowsError && <p className="reference-guidance is-warning">{flowsError}</p>}
          <div className="studio-model-list">
            {flows.map((flow) => (
              <span className="studio-model-chip" key={flow.name} title={flow.model}>
                <strong>{flow.name}</strong>
                <small>
                  {flow.steps} steps · CFG {flow.cfg}
                </small>
              </span>
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
