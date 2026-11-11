import { useState, type FormEvent } from "react";
import { defaultApiBase, getApiBase, setApiBase } from "../api/client";

function normalize(value: string): string {
  let next = value.trim().replace(/\/+$/, "");
  if (!next) return "";
  if (!/^https?:\/\//i.test(next)) next = `http://${next}`;
  return next;
}

function isValidBase(value: string): boolean {
  try {
    const parsed = new URL(value);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

/**
 * Shown when the UI cannot reach the backend. Lets the user point this browser
 * at another backend origin (LAN address or a fresh Cloudflare tunnel URL)
 * without rebuilding the GitHub Pages site.
 */
export function BackendOverride() {
  const [value, setValue] = useState(() => getApiBase());
  const [error, setError] = useState<string | null>(null);

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const next = normalize(value);
    if (next && !isValidBase(next)) {
      setError("http:// 또는 https:// 로 시작하는 주소를 입력해 주세요.");
      return;
    }
    setError(null);
    setApiBase(next);
    window.location.reload();
  };

  const reset = () => {
    setApiBase("");
    window.location.reload();
  };

  const fallback = defaultApiBase();

  return (
    <form className="backend-override" onSubmit={submit}>
      <label className="field-label" htmlFor="backend-base">
        백엔드 주소
      </label>
      <div className="backend-override-row">
        <input
          id="backend-base"
          className="backend-input"
          type="text"
          inputMode="url"
          spellCheck={false}
          placeholder={fallback || "http://192.168.0.3:8765"}
          value={value}
          onChange={(event) => setValue(event.target.value)}
        />
        <button className="btn btn-primary" type="submit">
          연결
        </button>
        {fallback && (
          <button className="btn btn-ghost" type="button" onClick={reset}>
            기본값
          </button>
        )}
      </div>
      <span className="field-foot">
        이 PC의 백엔드 주소를 입력하세요. 예: https://....trycloudflare.com 또는
        http://192.168.0.3:8765
      </span>
      {error && <span className="backend-override-error">{error}</span>}
    </form>
  );
}
