import { useEffect, useState } from "react";
import type { StudioStatus } from "../types";
import { assetUrl } from "../api/client";
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
  useEffect(() => {
    setFrameLoaded(false);
  }, [refreshKey]);

  const installed = status?.installed ?? false;
  const running = status?.running ?? false;
  const allowed = status?.allowed ?? true;
  const blocked = status?.remote_blocked ?? false;

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
              disabled={starting || !allowed}
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

      {installed && blocked && (
        <div className="studio-empty">
          <AlertIcon size={18} />
          <div>
            <strong>이 창에서는 작업실을 열 수 없습니다</strong>
            <p>
              nk 작업실은 이 PC 전용입니다. 같은 PC 에서
              <code> http://127.0.0.1:8765 </code>로 열어 주세요. 원격에서도 쓰려면
              <code> studio.allow_remote: true</code> 로 바꾸면 됩니다.
            </p>
          </div>
        </div>
      )}

      {installed && allowed && (
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
