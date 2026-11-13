import { useEffect, useMemo, useState } from "react";
import type {
  ComicStudioCandidate,
  ComicStudioCharacter,
  ComicStudioCut,
  ComicStudioProject,
  ComicStudioProjectSummary,
  ModelFile,
} from "../types";
import { api, assetUrl } from "../api/client";
import {
  AlertIcon,
  CheckIcon,
  DownloadIcon,
  ImageIcon,
  InfoIcon,
  PlayIcon,
  RefreshIcon,
  SparkIcon,
  TrashIcon,
} from "./Icons";

interface ComicStudioPanelProps {
  models: ModelFile[];
}

type ComicStudioMode = "nk" | "simple";

function initialComicMode(): ComicStudioMode {
  try {
    return localStorage.getItem("pixelforge.comicStudio.mode") === "simple"
      ? "simple"
      : "nk";
  } catch {
    return "nk";
  }
}

const LAYOUTS = [
  { id: "", label: "자동" },
  { id: "1x1", label: "1컷" },
  { id: "2x1", label: "2컷 세로" },
  { id: "1x2", label: "2컷 가로" },
  { id: "3x1", label: "3컷 세로" },
  { id: "2x2", label: "4컷" },
  { id: "2x3", label: "6컷" },
];

const EMPTY_CHARACTER = {
  id: "",
  name: "",
  adult: true,
  gender: "female",
  tags: "",
  default_outfit: "",
  negative: "",
  description: "",
};

function comicModels(models: ModelFile[]): ModelFile[] {
  return models.filter(
    (model) => model.compatible && (model.category === "image" || model.category === "pixel"),
  );
}

function defaultModel(models: ModelFile[]): string {
  const usable = comicModels(models);
  return (
    usable.find((model) => model.name.toLowerCase().includes("lustify"))?.name ??
    usable.find((model) => model.nsfw)?.name ??
    usable[0]?.name ??
    ""
  );
}

function candidateLabel(candidate: ComicStudioCandidate): string {
  return `${candidate.name} · seed ${candidate.seed}`;
}

function NkStudioFrame() {
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setState("loading");
    setError("");
    fetch("/api/nk-studio/start", { method: "POST" })
      .then(async (response) => {
        if (!response.ok) {
          const text = await response.text();
          throw new Error(text || `HTTP ${response.status}`);
        }
        if (!cancelled) setState("ready");
      })
      .catch((cause: unknown) => {
        if (cancelled) return;
        setState("error");
        setError(cause instanceof Error ? cause.message : "NK 작업실을 시작하지 못했습니다.");
      });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  if (state === "loading") {
    return (
      <div className="comic-nk-loading">
        <span className="spinner" />
        <div>
          <strong>NK 무검열 작업실을 시작하는 중…</strong>
          <span>nk 원본 런타임에서 safe 태그만 제거한 복사본을 띄웁니다.</span>
        </div>
      </div>
    );
  }
  if (state === "error") {
    return (
      <div className="comic-nk-error">
        <strong>NK 무검열 작업실을 열지 못했습니다.</strong>
        <pre>{error}</pre>
        <button type="button" className="btn btn-small" onClick={() => setAttempt((n) => n + 1)}>
          다시 시도
        </button>
      </div>
    );
  }
  return (
    <div className="comic-nk-frame">
      <iframe src="/nk-studio/" title="NK 무검열 작업실" />
    </div>
  );
}

export function ComicStudioPanel({ models }: ComicStudioPanelProps) {
  const usableModels = useMemo(() => comicModels(models), [models]);
  const [mode, setMode] = useState<ComicStudioMode>(initialComicMode);

  const switchMode = (next: ComicStudioMode) => {
    setMode(next);
    try {
      localStorage.setItem("pixelforge.comicStudio.mode", next);
    } catch {
      // localStorage can be disabled; the in-memory state still works.
    }
  };

  const [projects, setProjects] = useState<ComicStudioProjectSummary[]>([]);
  const [projectsLoading, setProjectsLoading] = useState(false);
  const [selectedId, setSelectedId] = useState("");
  const [project, setProject] = useState<ComicStudioProject | null>(null);
  const [projectLoading, setProjectLoading] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [newTitle, setNewTitle] = useState("새 만화");
  const [newModel, setNewModel] = useState("");
  const [creating, setCreating] = useState(false);

  const [editorTitle, setEditorTitle] = useState("");
  const [editorModel, setEditorModel] = useState("");
  const [editorYaml, setEditorYaml] = useState("");
  const [saving, setSaving] = useState(false);
  const [compiling, setCompiling] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const [genCount, setGenCount] = useState(2);
  const [genSeeds, setGenSeeds] = useState("");
  const [genSteps, setGenSteps] = useState("");
  const [genCfg, setGenCfg] = useState("");
  const [genExtra, setGenExtra] = useState("");
  const [generatingCutId, setGeneratingCutId] = useState<number | null>(null);
  const [pickingCutId, setPickingCutId] = useState<number | null>(null);
  const [batchDrawing, setBatchDrawing] = useState(false);
  const [batchProgress, setBatchProgress] = useState<{
    done: number;
    total: number;
    cutId: number;
  } | null>(null);
  const [assemblingAll, setAssemblingAll] = useState(false);
  const [assembleProgress, setAssembleProgress] = useState<{
    done: number;
    total: number;
    page: number;
  } | null>(null);

  const [layouts, setLayouts] = useState<Record<number, string>>({});
  const [buildingPage, setBuildingPage] = useState<number | null>(null);

  const [characterForm, setCharacterForm] = useState({ ...EMPTY_CHARACTER });
  const [characterBusy, setCharacterBusy] = useState(false);

  useEffect(() => {
    if (!newModel && usableModels.length > 0) {
      setNewModel(defaultModel(usableModels));
    }
  }, [newModel, usableModels]);

  const loadProjects = async (select?: string) => {
    setProjectsLoading(true);
    try {
      const response = await api.getComicStudioProjects();
      setProjects(response.items ?? []);
      setSelectedId((current) => {
        const wanted = select ?? current;
        if (wanted && response.items.some((item) => item.id === wanted)) return wanted;
        return response.items[0]?.id ?? "";
      });
    } catch (cause) {
      setActionError(
        cause instanceof Error ? cause.message : "프로젝트 목록을 불러오지 못했습니다.",
      );
    } finally {
      setProjectsLoading(false);
    }
  };

  const loadProject = async (projectId: string) => {
    setProjectLoading(true);
    setActionError(null);
    try {
      const detail = await api.getComicStudioProject(projectId);
      setProject(detail);
      setEditorTitle(detail.title);
      setEditorModel(detail.model);
      setEditorYaml(detail.plan_yaml);
    } catch (cause) {
      setProject(null);
      setActionError(
        cause instanceof Error ? cause.message : "프로젝트를 불러오지 못했습니다.",
      );
    } finally {
      setProjectLoading(false);
    }
  };

  useEffect(() => {
    void loadProjects();
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setProject(null);
      return;
    }
    void loadProject(selectedId);
  }, [selectedId]);

  const refreshProject = async (projectId: string) => {
    const detail = await api.getComicStudioProject(projectId);
    setProject(detail);
    return detail;
  };

  const createProject = async () => {
    if (!newTitle.trim() || creating) return;
    setCreating(true);
    setActionError(null);
    setNotice(null);
    try {
      const created = await api.createComicStudioProject({
        title: newTitle.trim(),
        model: newModel || defaultModel(usableModels),
      });
      await loadProjects(created.id);
      setSelectedId(created.id);
      setProject(created);
      setEditorTitle(created.title);
      setEditorModel(created.model);
      setEditorYaml(created.plan_yaml);
      setNotice("새 만화 프로젝트를 만들었습니다. 콘티를 고치고 「저장 + 컴파일」을 누르세요.");
    } catch (cause) {
      setActionError(
        cause instanceof Error ? cause.message : "프로젝트를 만들지 못했습니다.",
      );
    } finally {
      setCreating(false);
    }
  };

  const saveProject = async () => {
    if (!project || saving) return;
    setSaving(true);
    setActionError(null);
    setNotice(null);
    try {
      const updated = await api.updateComicStudioProject(project.id, {
        title: editorTitle,
        model: editorModel,
        plan_yaml: editorYaml,
      });
      setProject(updated);
      setEditorTitle(updated.title);
      setEditorModel(updated.model);
      setEditorYaml(updated.plan_yaml);
      setNotice(
        updated.error
          ? `저장했습니다. 콘티 오류: ${updated.error}`
          : `저장했습니다. ${updated.cuts.length}컷 · ${updated.plan_pages.length}페이지`,
      );
      await loadProjects(project.id);
    } catch (cause) {
      setActionError(cause instanceof Error ? cause.message : "저장하지 못했습니다.");
    } finally {
      setSaving(false);
    }
  };

  const compileProject = async () => {
    if (!project || compiling) return;
    setCompiling(true);
    setActionError(null);
    setNotice(null);
    try {
      const result = await api.compileComicStudioProject(project.id);
      const detail = await refreshProject(project.id);
      setNotice(
        `컴파일 완료: ${result.cuts}컷 · ${result.pages}페이지${
          result.warnings.length ? ` · 경고 ${result.warnings.length}개` : ""
        }`,
      );
      setEditorYaml(detail.plan_yaml);
    } catch (cause) {
      setActionError(cause instanceof Error ? cause.message : "컴파일하지 못했습니다.");
    } finally {
      setCompiling(false);
    }
  };

  const deleteProject = async () => {
    if (!project || deleting) return;
    if (!window.confirm(`"${project.title}" 프로젝트와 생성된 후보를 모두 삭제할까요?`)) {
      return;
    }
    setDeleting(true);
    setActionError(null);
    try {
      await api.deleteComicStudioProject(project.id);
      setProject(null);
      setSelectedId("");
      setNotice("프로젝트를 삭제했습니다.");
      await loadProjects();
    } catch (cause) {
      setActionError(cause instanceof Error ? cause.message : "삭제하지 못했습니다.");
    } finally {
      setDeleting(false);
    }
  };

  const updateCut = (next: ComicStudioCut) => {
    setProject((current) =>
      current
        ? { ...current, cuts: current.cuts.map((cut) => (cut.id === next.id ? next : cut)) }
        : current,
    );
  };

  const generationPayload = () => ({
    seeds: genSeeds.trim() || undefined,
    count: genCount,
    model: editorModel || project?.model || undefined,
    steps: genSteps.trim() ? Number(genSteps) : undefined,
    cfg: genCfg.trim() ? Number(genCfg) : undefined,
    prompt_extra: genExtra.trim() || undefined,
  });

  const generateCut = async (cut: ComicStudioCut) => {
    if (!project || generatingCutId !== null) return;
    setGeneratingCutId(cut.id);
    setActionError(null);
    setNotice(null);
    try {
      const result = await api.generateComicStudioCut(
        project.id,
        cut.id,
        generationPayload(),
      );
      updateCut(result.cut);
      setNotice(
        `${cut.id}번 컷에 ${result.generated.length}장을 추가했습니다. ` +
          `모델 ${result.model} · seed ${result.generated.map((item) => item.seed).join(", ")}`,
      );
      await loadProjects(project.id);
    } catch (cause) {
      setActionError(cause instanceof Error ? cause.message : "컷을 그리지 못했습니다.");
    } finally {
      setGeneratingCutId(null);
    }
  };

  const generateAllCuts = async () => {
    if (!project || batchDrawing || generatingCutId !== null || assemblingAll) return;
    if (project.error) {
      setActionError(`콘티 오류를 먼저 고쳐 주세요. ${project.error}`);
      return;
    }
    const cuts = project.cuts;
    if (cuts.length === 0) {
      setActionError("컴파일된 컷이 없습니다. 콘티를 먼저 저장·컴파일해 주세요.");
      return;
    }
    setBatchDrawing(true);
    setActionError(null);
    setNotice(null);
    let produced = 0;
    try {
      for (const [index, cut] of cuts.entries()) {
        setBatchProgress({ done: index, total: cuts.length, cutId: cut.id });
        const result = await api.generateComicStudioCut(
          project.id,
          cut.id,
          generationPayload(),
        );
        updateCut(result.cut);
        produced += result.generated.length;
      }
      setBatchProgress({ done: cuts.length, total: cuts.length, cutId: 0 });
      const detail = await api.getComicStudioProject(project.id);
      setProject(detail);
      const missing = detail.cuts.filter((cut) => !cut.selected).length;
      setNotice(
        `${cuts.length}컷에 후보 ${produced}장을 만들었습니다. ` +
          (missing > 0
            ? `컷마다 후보를 골라 주세요. 아직 ${missing}컷이 선택 전입니다.`
            : "모든 컷이 선택되었습니다. 「전체 페이지 조립」을 누르세요."),
      );
      await loadProjects(project.id);
    } catch (cause) {
      setActionError(
        `한번에 만들기가 중간에 멈췄습니다. ${
          cause instanceof Error ? cause.message : "컷을 그리지 못했습니다."
        }`,
      );
    } finally {
      setBatchDrawing(false);
      setBatchProgress(null);
    }
  };

  const pickCandidate = async (cut: ComicStudioCut, candidate: ComicStudioCandidate) => {
    if (!project || pickingCutId !== null) return;
    setPickingCutId(cut.id);
    setActionError(null);
    try {
      const next = await api.pickComicStudioCandidate(project.id, cut.id, candidate.name);
      updateCut(next);
      setNotice(`${cut.id}번 컷의 최종 이미지를 ${candidate.name} 로 골랐습니다.`);
      await loadProjects(project.id);
    } catch (cause) {
      setActionError(cause instanceof Error ? cause.message : "후보를 고르지 못했습니다.");
    } finally {
      setPickingCutId(null);
    }
  };

  const clearPick = async (cut: ComicStudioCut) => {
    if (!project || pickingCutId !== null) return;
    setPickingCutId(cut.id);
    setActionError(null);
    try {
      const next = await api.clearComicStudioPick(project.id, cut.id);
      updateCut(next);
    } catch (cause) {
      setActionError(cause instanceof Error ? cause.message : "선택을 해제하지 못했습니다.");
    } finally {
      setPickingCutId(null);
    }
  };

  const deleteCandidate = async (cut: ComicStudioCut, candidate: ComicStudioCandidate) => {
    if (!project) return;
    if (!window.confirm(`${candidate.name} 후보를 삭제할까요?`)) return;
    setActionError(null);
    try {
      const next = await api.deleteComicStudioCandidate(project.id, cut.id, candidate.name);
      updateCut(next);
      await loadProjects(project.id);
    } catch (cause) {
      setActionError(cause instanceof Error ? cause.message : "후보를 삭제하지 못했습니다.");
    }
  };

  const buildPage = async (pageNumber: number) => {
    if (!project || buildingPage !== null || assemblingAll || batchDrawing) return;
    setBuildingPage(pageNumber);
    setActionError(null);
    setNotice(null);
    try {
      const layout = layouts[pageNumber] || undefined;
      const page = await api.buildComicStudioPage(project.id, {
        page: pageNumber,
        layout,
        width: 1240,
        height: 1754,
        title: editorTitle || project.title,
      });
      setProject((current) =>
        current
          ? {
              ...current,
              pages: [
                ...current.pages.filter((item) => item.number !== pageNumber),
                page,
              ].sort((a, b) => a.number - b.number),
            }
          : current,
      );
      setNotice(`${pageNumber}페이지를 조립했습니다. PNG/PDF로 내려받을 수 있습니다.`);
      await loadProjects(project.id);
    } catch (cause) {
      setActionError(cause instanceof Error ? cause.message : "페이지를 조립하지 못했습니다.");
    } finally {
      setBuildingPage(null);
    }
  };

  const assembleAllPages = async () => {
    if (!project || assemblingAll || buildingPage !== null || batchDrawing) return;
    const planPages = project.plan_pages;
    if (planPages.length === 0) {
      setActionError("컴파일된 페이지가 없습니다. 콘티를 먼저 저장·컴파일해 주세요.");
      return;
    }
    const selected = new Map(project.cuts.map((cut) => [cut.id, cut.selected]));
    const missing: number[] = [];
    for (const page of planPages) {
      for (const cutId of page.cut_ids) {
        if (!selected.get(cutId)) missing.push(cutId);
      }
    }
    if (missing.length > 0) {
      const unique = [...new Set(missing)];
      setActionError(
        `컷 ${unique.join(", ")} 의 최종 이미지가 아직 없습니다. ` +
          "컷마다 후보를 하나씩 고른 뒤 다시 눌러 주세요.",
      );
      return;
    }
    setAssemblingAll(true);
    setActionError(null);
    setNotice(null);
    let built = 0;
    try {
      for (const [index, page] of planPages.entries()) {
        setAssembleProgress({
          done: index,
          total: planPages.length,
          page: page.number,
        });
        const result = await api.buildComicStudioPage(project.id, {
          page: page.number,
          layout: layouts[page.number] || undefined,
          width: 1240,
          height: 1754,
          title: editorTitle || project.title,
        });
        setProject((current) =>
          current
            ? {
                ...current,
                pages: [
                  ...current.pages.filter((item) => item.number !== page.number),
                  result,
                ].sort((a, b) => a.number - b.number),
              }
            : current,
        );
        built += 1;
      }
      const detail = await api.getComicStudioProject(project.id);
      setProject(detail);
      setNotice(
        `${built}페이지 만화를 조립했습니다. 「전체 PDF」로 내려받거나 페이지별 PDF를 열 수 있습니다.`,
      );
      await loadProjects(project.id);
    } catch (cause) {
      setActionError(
        `전체 페이지 조립이 중간에 멈췄습니다. ${
          cause instanceof Error ? cause.message : "페이지를 조립하지 못했습니다."
        }`,
      );
    } finally {
      setAssemblingAll(false);
      setAssembleProgress(null);
    }
  };

  const deletePage = async (pageNumber: number) => {
    if (!project) return;
    if (!window.confirm(`${pageNumber}페이지를 삭제할까요?`)) return;
    setActionError(null);
    try {
      await api.deleteComicStudioPage(project.id, pageNumber);
      setProject((current) =>
        current
          ? { ...current, pages: current.pages.filter((page) => page.number !== pageNumber) }
          : current,
      );
      await loadProjects(project.id);
    } catch (cause) {
      setActionError(cause instanceof Error ? cause.message : "페이지를 삭제하지 못했습니다.");
    }
  };

  const saveCharacter = async () => {
    if (!project || characterBusy) return;
    setCharacterBusy(true);
    setActionError(null);
    try {
      await api.saveComicStudioCharacter(characterForm);
      const detail = await refreshProject(project.id);
      setProject(detail);
      setCharacterForm({ ...EMPTY_CHARACTER });
      setNotice("캐릭터를 저장했습니다. 콘티의 cast 에서 ID를 쓰세요.");
    } catch (cause) {
      setActionError(cause instanceof Error ? cause.message : "캐릭터를 저장하지 못했습니다.");
    } finally {
      setCharacterBusy(false);
    }
  };

  const deleteCharacter = async (character: ComicStudioCharacter) => {
    if (!project || character.builtin) return;
    if (!window.confirm(`캐릭터 "${character.name}" 을(를) 삭제할까요?`)) return;
    setActionError(null);
    try {
      await api.deleteComicStudioCharacter(character.id);
      const detail = await refreshProject(project.id);
      setProject(detail);
    } catch (cause) {
      setActionError(cause instanceof Error ? cause.message : "캐릭터를 삭제하지 못했습니다.");
    }
  };

  const groupedCuts = useMemo(() => {
    if (!project) return [] as Array<{ page: number; note: string; cuts: ComicStudioCut[] }>;
    const cutById = new Map(project.cuts.map((cut) => [cut.id, cut]));
    const pages =
      project.plan_pages.length > 0
        ? project.plan_pages
        : Array.from(new Set(project.cuts.map((cut) => cut.page))).map((page) => ({
            number: page,
            note: "",
            cut_ids: project.cuts.filter((cut) => cut.page === page).map((cut) => cut.id),
          }));
    return pages.map((page) => ({
      page: page.number,
      note: page.note,
      cuts: page.cut_ids.map((id) => cutById.get(id)).filter((cut): cut is ComicStudioCut => Boolean(cut)),
    }));
  }, [project]);

  const pickedCount = project?.cuts.filter((cut) => cut.selected).length ?? 0;
  const candidateCount =
    project?.cuts.reduce((total, cut) => total + cut.candidates.length, 0) ?? 0;
  const pageCount = project?.pages.length ?? 0;
  const busy =
    batchDrawing ||
    assemblingAll ||
    generatingCutId !== null ||
    pickingCutId !== null;

  if (mode === "nk") {
    return (
      <section className="panel studio-panel comic-studio-panel is-nk-mode">
        <div className="panel-head">
          <div>
            <span className="eyebrow">05 · COMIC STUDIO</span>
            <h2>
              만화 스튜디오 <span className="comic-mode-badge">NK 그대로 · safe 제거</span>
            </h2>
          </div>
          <div className="studio-head-actions">
            <button
              type="button"
              className="btn btn-small"
              onClick={() => switchMode("simple")}
            >
              <SparkIcon size={13} /> 간편 모드
            </button>
            <a
              className="btn btn-small"
              href="/nk-studio/"
              target="_blank"
              rel="noreferrer"
            >
              <ImageIcon size={13} /> 새 창으로 열기
            </a>
          </div>
        </div>

        <div className="comic-mode-bar">
          <div>
            <strong>NK 원본 작업실 + safe 제거</strong>
            <span>
              nk의 새 만화 · 콘티 컴파일 · 후보 생성 · 자동 검수 · 선택 · 글자/쪽 · 표지 ·
              PDF 흐름을 그대로 씁니다. 프롬프트에서 safe 태그만 빠집니다.
            </span>
          </div>
          <em>기존 nk 에피소드 공유</em>
        </div>

        <NkStudioFrame />

        <div className="comic-mode-note">
          <InfoIcon size={14} />
          <span>
            이 모드는 실제 nk 런타임을 실행합니다. 원본 nk는 수정하지 않고, 로컬 패치
            복사본만 safe 태그를 제거합니다. 성인 캐릭터만 사용하고 실제 인물·미성년자는
            넣지 마세요.
          </span>
        </div>
      </section>
    );
  }

  return (
    <section className="panel studio-panel comic-studio-panel">
      <div className="panel-head">
        <div>
          <span className="eyebrow">05 · COMIC STUDIO</span>
          <h2>만화 스튜디오</h2>
        </div>
        <div className="studio-head-actions">
          <span className="studio-state ok">
            <CheckIcon size={12} /> 무검열 모델
          </span>
          <button
            type="button"
            className="btn btn-small"
            onClick={() => switchMode("nk")}
            disabled={busy}
          >
            <SparkIcon size={13} /> NK 그대로 모드
          </button>
          <button
            type="button"
            className="icon-button"
            onClick={() => {
              void loadProjects(selectedId);
              if (selectedId) void loadProject(selectedId);
            }}
            title="새로고침"
            disabled={busy}
          >
            <RefreshIcon size={14} />
          </button>
        </div>
      </div>

      <div className="studio-note">
        <InfoIcon size={14} />
        <span>
          nk와 별개로 동작하는 자체 만화 제작기입니다. 콘티 YAML을 컴파일해 컷 프롬프트를
          만들고, 로컬 ComfyUI에서 후보를 뽑은 뒤 골라서 페이지·PDF로 묶습니다.{" "}
          <strong>「한번에 만들기」로 모든 컷 후보를 한 번에 생성하고, 후보를 고른 뒤
          「전체 페이지 조립」을 누르면 됩니다.</strong> 프롬프트에 safe 태그를 자동으로
          넣지 않습니다. 성인 캐릭터만 사용하고, 실제 인물·미성년자는 넣지 마세요.
        </span>
      </div>

      <div className="comic-studio-layout">
        <aside className="comic-projects">
          <div className="comic-new">
            <span className="field-label">새 만화</span>
            <input
              value={newTitle}
              onChange={(event) => setNewTitle(event.target.value)}
              placeholder="제목"
              maxLength={120}
            />
            <select value={newModel} onChange={(event) => setNewModel(event.target.value)}>
              {usableModels.map((model) => (
                <option value={model.name} key={model.name}>
                  {model.name}
                  {model.nsfw ? " · 19+" : ""}
                </option>
              ))}
            </select>
            <button
              type="button"
              className="btn btn-primary btn-small"
              onClick={() => void createProject()}
              disabled={creating || !newTitle.trim() || busy}
            >
              {creating ? <span className="spinner" /> : <SparkIcon size={13} />} 새 만화
            </button>
          </div>

          <div className="comic-project-list">
            {projectsLoading && projects.length === 0 && (
              <span className="setting-note">불러오는 중...</span>
            )}
            {projects.map((item) => (
              <button
                type="button"
                key={item.id}
                className={`comic-project-item ${selectedId === item.id ? "is-selected" : ""}`}
                onClick={() => setSelectedId(item.id)}
                disabled={busy}
              >
                <span className="comic-project-cover">
                  {item.cover_url ? (
                    <img src={assetUrl(item.cover_url)} alt="" />
                  ) : (
                    <ImageIcon size={18} />
                  )}
                </span>
                <span className="comic-project-copy">
                  <strong>{item.title}</strong>
                  <small>
                    {item.cut_count}컷 · {item.picked_count}/{item.cut_count} 선택 ·{" "}
                    {item.page_count}페이지
                  </small>
                  {item.error && <em>콘티 오류</em>}
                </span>
              </button>
            ))}
            {!projectsLoading && projects.length === 0 && (
              <span className="setting-note">아직 만화가 없습니다. 위에서 새로 만드세요.</span>
            )}
          </div>
        </aside>

        <div className="comic-editor">
          {actionError && (
            <div className="studio-error">
              <AlertIcon size={16} />
              <span>{actionError}</span>
            </div>
          )}
          {notice && (
            <div className="comic-notice">
              <CheckIcon size={14} />
              <span>{notice}</span>
            </div>
          )}

          {!selectedId && !projectLoading && (
            <div className="studio-empty">
              <ImageIcon size={20} />
              <div>
                <strong>새 만화를 만들거나 왼쪽에서 프로젝트를 고르세요</strong>
                <p>콘티 YAML을 저장하면 컷 목록과 프롬프트가 자동으로 만들어집니다.</p>
              </div>
            </div>
          )}

          {projectLoading && (
            <div className="studio-empty">
              <span className="spinner" />
              <div>
                <strong>프로젝트를 불러오는 중...</strong>
              </div>
            </div>
          )}

          {project && !projectLoading && (
            <>
              <div className="comic-toolbar">
                <label>
                  <span>제목</span>
                  <input
                    value={editorTitle}
                    onChange={(event) => setEditorTitle(event.target.value)}
                    maxLength={120}
                  />
                </label>
                <label>
                  <span>모델</span>
                  <select
                    value={editorModel}
                    onChange={(event) => setEditorModel(event.target.value)}
                  >
                    {editorModel && !usableModels.some((model) => model.name === editorModel) && (
                      <option value={editorModel}>{editorModel}</option>
                    )}
                    {usableModels.map((model) => (
                      <option value={model.name} key={model.name}>
                        {model.name}
                        {model.nsfw ? " · 19+" : ""}
                      </option>
                    ))}
                  </select>
                </label>
                <div className="comic-toolbar-actions">
                  <button
                    type="button"
                    className="btn btn-primary btn-small"
                    onClick={() => void saveProject()}
                    disabled={saving || busy}
                  >
                    {saving ? <span className="spinner" /> : <CheckIcon size={13} />} 저장 + 컴파일
                  </button>
                  <button
                    type="button"
                    className="btn btn-small"
                    onClick={() => void compileProject()}
                    disabled={compiling || busy}
                  >
                    {compiling ? <span className="spinner" /> : <PlayIcon size={13} />} 컴파일
                  </button>
                  <button
                    type="button"
                    className="icon-button"
                    title="프로젝트 삭제"
                    onClick={() => void deleteProject()}
                    disabled={deleting || busy}
                  >
                    <TrashIcon size={14} />
                  </button>
                </div>
              </div>

              <div className="comic-stats">
                <span>{project.cuts.length}컷</span>
                <span>{candidateCount}후보</span>
                <span>{pickedCount}선택</span>
                <span>{pageCount}페이지</span>
                <span>{project.plan_pages.length}계획 페이지</span>
              </div>

              <div className="comic-batch">
                <div className="comic-batch-copy">
                  <strong>한번에 만들기</strong>
                  <span>후보 일괄 생성 → 컷별 후보 선택 → 전체 페이지 조립</span>
                  <em>
                    {pickedCount}/{project.cuts.length}컷 선택
                  </em>
                </div>
                <div className="comic-batch-actions">
                  <button
                    type="button"
                    className="btn btn-primary btn-small"
                    onClick={() => void generateAllCuts()}
                    disabled={busy || project.cuts.length === 0}
                  >
                    {batchDrawing ? <span className="spinner" /> : <SparkIcon size={13} />}
                    {batchDrawing && batchProgress
                      ? `후보 생성 중 ${batchProgress.done + 1}/${batchProgress.total}`
                      : `후보 일괄 생성 (${project.cuts.length}컷 × ${genCount}장)`}
                  </button>
                  <button
                    type="button"
                    className="btn btn-small"
                    onClick={() => void assembleAllPages()}
                    disabled={busy}
                  >
                    {assemblingAll ? <span className="spinner" /> : <ImageIcon size={13} />}
                    전체 페이지 조립
                  </button>
                </div>
              </div>

              {batchDrawing && batchProgress && (
                <div className="comic-batch-progress">
                  <span
                    style={{
                      width: `${Math.round(
                        ((batchProgress.done + 1) / batchProgress.total) * 100,
                      )}%`,
                    }}
                  />
                  <em>
                    {batchProgress.done + 1}/{batchProgress.total}컷 · #
                    {batchProgress.cutId} 그리는 중
                  </em>
                </div>
              )}
              {assemblingAll && assembleProgress && (
                <div className="comic-batch-progress is-page">
                  <span
                    style={{
                      width: `${Math.round(
                        ((assembleProgress.done + 1) / assembleProgress.total) * 100,
                      )}%`,
                    }}
                  />
                  <em>
                    {assembleProgress.done + 1}/{assembleProgress.total}페이지 ·{" "}
                    {assembleProgress.page}페이지 조립 중
                  </em>
                </div>
              )}

              <div className="comic-plan">
                <div className="comic-plan-head">
                  <span className="field-label">plan.yaml</span>
                  <span className="setting-note">
                    콘티를 고친 뒤 저장하면 컷 프롬프트가 다시 만들어집니다.
                  </span>
                </div>
                <textarea
                  value={editorYaml}
                  onChange={(event) => setEditorYaml(event.target.value)}
                  spellCheck={false}
                  rows={18}
                />
              </div>

              {project.error && (
                <div className="studio-error">
                  <AlertIcon size={16} />
                  <span>콘티 오류: {project.error}</span>
                </div>
              )}
              {project.warnings.length > 0 && (
                <details className="comic-warnings">
                  <summary>
                    <AlertIcon size={13} /> 컴파일 경고 {project.warnings.length}개
                  </summary>
                  <ul>
                    {project.warnings.map((warning, index) => (
                      <li key={`${warning}-${index}`}>{warning}</li>
                    ))}
                  </ul>
                </details>
              )}

              <div className="comic-gen-settings">
                <span className="field-label">
                  <ImageIcon size={13} /> 후보 생성 설정
                </span>
                <div className="comic-gen-grid">
                  <label>
                    <span>장수</span>
                    <select
                      value={genCount}
                      onChange={(event) => setGenCount(Number(event.target.value))}
                      disabled={busy}
                    >
                      {[1, 2, 3, 4].map((value) => (
                        <option value={value} key={value}>
                          {value}장
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    <span>시드</span>
                    <input
                      value={genSeeds}
                      onChange={(event) => setGenSeeds(event.target.value)}
                      disabled={busy}
                      placeholder="비우면 랜덤, 예: 101,102"
                    />
                  </label>
                  <label>
                    <span>스텝</span>
                    <input
                      value={genSteps}
                      onChange={(event) => setGenSteps(event.target.value)}
                      disabled={busy}
                      placeholder="자동"
                    />
                  </label>
                  <label>
                    <span>CFG</span>
                    <input
                      value={genCfg}
                      onChange={(event) => setGenCfg(event.target.value)}
                      disabled={busy}
                      placeholder="자동"
                    />
                  </label>
                </div>
                <input
                  className="comic-extra-input"
                  value={genExtra}
                  onChange={(event) => setGenExtra(event.target.value)}
                  disabled={busy}
                  placeholder="추가 프롬프트 태그 (선택)"
                />
              </div>

              <div className="comic-cut-list">
                {groupedCuts.map((group) => (
                  <div className="comic-page-group" key={group.page}>
                    <div className="comic-page-head">
                      <strong>{group.page}페이지</strong>
                      {group.note && <span>{group.note}</span>}
                      <em>{group.cuts.length}컷</em>
                    </div>
                    {group.cuts.map((cut) => (
                      <CutCard
                        key={cut.id}
                        cut={cut}
                        busy={busy}
                        generating={generatingCutId === cut.id}
                        picking={pickingCutId === cut.id}
                        onGenerate={() => void generateCut(cut)}
                        onPick={(candidate) => void pickCandidate(cut, candidate)}
                        onClearPick={() => void clearPick(cut)}
                        onDeleteCandidate={(candidate) => void deleteCandidate(cut, candidate)}
                      />
                    ))}
                  </div>
                ))}
                {project.cuts.length === 0 && !project.error && (
                  <span className="setting-note">
                    컴파일된 컷이 없습니다. plan.yaml 의 pages/cuts 를 확인하세요.
                  </span>
                )}
              </div>

              <div className="comic-pages">
                <div className="comic-pages-head">
                  <span className="field-label">페이지 · PDF</span>
                  {project.pages.length > 0 && (
                    <a
                      className="text-button"
                      href={assetUrl(`/api/comic-studio/projects/${project.id}/export.pdf`)}
                      target="_blank"
                      rel="noreferrer"
                    >
                      <DownloadIcon size={13} /> 전체 PDF
                    </a>
                  )}
                </div>
                <div className="comic-page-grid">
                  {project.plan_pages.map((page) => {
                    const built = project.pages.find((item) => item.number === page.number);
                    return (
                      <div className="comic-page-card" key={page.number}>
                        <div className="comic-page-card-head">
                          <strong>{page.number}페이지</strong>
                          <select
                            value={layouts[page.number] ?? ""}
                            onChange={(event) =>
                              setLayouts((current) => ({
                                ...current,
                                [page.number]: event.target.value,
                              }))
                            }
                          >
                            {LAYOUTS.map((layout) => (
                              <option value={layout.id} key={layout.id}>
                                {layout.label}
                              </option>
                            ))}
                          </select>
                        </div>
                        {built ? (
                          <a
                            className="comic-page-thumb"
                            href={assetUrl(built.image_url)}
                            target="_blank"
                            rel="noreferrer"
                          >
                            <img src={assetUrl(built.image_url)} alt={`${page.number}페이지`} />
                          </a>
                        ) : (
                          <div className="comic-page-thumb is-empty">
                            <ImageIcon size={22} />
                            <span>아직 조립 전</span>
                          </div>
                        )}
                        <div className="comic-page-actions">
                          <button
                            type="button"
                            className="btn btn-primary btn-small"
                            onClick={() => void buildPage(page.number)}
                            disabled={buildingPage !== null || assemblingAll || batchDrawing}
                          >
                            {buildingPage === page.number ? (
                              <span className="spinner" />
                            ) : (
                              <PlayIcon size={12} />
                            )}{" "}
                            {built ? "다시 조립" : "페이지 조립"}
                          </button>
                          {built && (
                            <>
                              <a
                                className="text-button"
                                href={assetUrl(built.pdf_url)}
                                target="_blank"
                                rel="noreferrer"
                              >
                                PDF
                              </a>
                              <button
                                type="button"
                                className="text-button is-danger"
                                onClick={() => void deletePage(page.number)}
                                disabled={assemblingAll || batchDrawing}
                              >
                                삭제
                              </button>
                            </>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
                {project.plan_pages.length === 0 && (
                  <span className="setting-note">
                    콘티가 컴파일되면 여기에 페이지별 조립 버튼이 나옵니다.
                  </span>
                )}
              </div>

              <details className="comic-characters">
                <summary>
                  <SparkIcon size={13} /> 캐릭터 라이브러리 ({project.characters.length})
                </summary>
                <div className="comic-character-list">
                  {project.characters.map((character) => (
                    <div className="comic-character-item" key={character.id}>
                      <div>
                        <strong>{character.name || character.id}</strong>
                        <small>
                          {character.id} · {character.gender} ·{" "}
                          {character.builtin ? "내장" : "사용자"}
                        </small>
                        <p>{character.tags}</p>
                      </div>
                      {!character.builtin && (
                        <button
                          type="button"
                          className="icon-button"
                          title="캐릭터 삭제"
                          onClick={() => void deleteCharacter(character)}
                        >
                          <TrashIcon size={13} />
                        </button>
                      )}
                    </div>
                  ))}
                </div>
                <div className="comic-character-form">
                  <span className="field-label">새 성인 캐릭터</span>
                  <div className="comic-character-grid">
                    <input
                      value={characterForm.id}
                      onChange={(event) =>
                        setCharacterForm((current) => ({ ...current, id: event.target.value }))
                      }
                      placeholder="ID (영문, 예: my_hero)"
                    />
                    <input
                      value={characterForm.name}
                      onChange={(event) =>
                        setCharacterForm((current) => ({ ...current, name: event.target.value }))
                      }
                      placeholder="표시 이름"
                    />
                    <select
                      value={characterForm.gender}
                      onChange={(event) =>
                        setCharacterForm((current) => ({ ...current, gender: event.target.value }))
                      }
                    >
                      <option value="female">여성</option>
                      <option value="male">남성</option>
                      <option value="other">기타</option>
                    </select>
                  </div>
                  <input
                    value={characterForm.tags}
                    onChange={(event) =>
                      setCharacterForm((current) => ({ ...current, tags: event.target.value }))
                    }
                    placeholder="외형 태그: 1girl, adult woman, black hair, ..."
                  />
                  <input
                    value={characterForm.default_outfit}
                    onChange={(event) =>
                      setCharacterForm((current) => ({
                        ...current,
                        default_outfit: event.target.value,
                      }))
                    }
                    placeholder="기본 의상 태그 (선택)"
                  />
                  <input
                    value={characterForm.description}
                    onChange={(event) =>
                      setCharacterForm((current) => ({
                        ...current,
                        description: event.target.value,
                      }))
                    }
                    placeholder="설명 (선택)"
                  />
                  <button
                    type="button"
                    className="btn btn-primary btn-small"
                    onClick={() => void saveCharacter()}
                    disabled={characterBusy || !characterForm.id.trim() || !characterForm.tags.trim()}
                  >
                    {characterBusy ? <span className="spinner" /> : <CheckIcon size={13} />} 캐릭터 저장
                  </button>
                  <p className="setting-note">
                    저장 위치: outputs/comic_studio/characters. 콘티에서는{" "}
                    <code>cast: {"{hero: my_hero}"}</code> 처럼 씁니다. adult: true 가
                    아니면 저장되지 않습니다.
                  </p>
                </div>
              </details>
            </>
          )}
        </div>
      </div>
    </section>
  );
}

interface CutCardProps {
  cut: ComicStudioCut;
  busy: boolean;
  generating: boolean;
  picking: boolean;
  onGenerate: () => void;
  onPick: (candidate: ComicStudioCandidate) => void;
  onClearPick: () => void;
  onDeleteCandidate: (candidate: ComicStudioCandidate) => void;
}

function CutCard({
  cut,
  busy,
  generating,
  picking,
  onGenerate,
  onPick,
  onClearPick,
  onDeleteCandidate,
}: CutCardProps) {
  return (
    <article className="comic-cut-card">
      <div className="comic-cut-head">
        <div>
          <strong>#{cut.id}</strong>
          <span>
            {cut.shot} · {cut.angle}
            {cut.loc ? ` · ${cut.loc}` : ""}
            {cut.who.length ? ` · ${cut.who.join(", ")}` : " · 배경"}
          </span>
          <small>
            {cut.width}×{cut.height}
          </small>
        </div>
        <div className="comic-cut-actions">
          <button
            type="button"
            className="btn btn-primary btn-small"
            onClick={onGenerate}
            disabled={busy}
          >
            {generating ? <span className="spinner" /> : <PlayIcon size={12} />} 후보 그리기
          </button>
          {cut.selected && (
            <button type="button" className="text-button" onClick={onClearPick} disabled={busy}>
              선택 해제
            </button>
          )}
        </div>
      </div>

      {cut.text && <p className="comic-cut-text">{cut.text}</p>}
      {cut.action && <p className="comic-cut-action">{cut.action}</p>}

      {cut.candidates.length > 0 ? (
        <div className="comic-candidate-row">
          {cut.candidates.map((candidate) => {
            const selected = cut.selected === candidate.name;
            return (
              <div
                className={`comic-candidate ${selected ? "is-selected" : ""}`}
                key={candidate.name}
              >
                <button
                  type="button"
                  className="comic-candidate-pick"
                  onClick={() => onPick(candidate)}
                  disabled={busy}
                  title={candidateLabel(candidate)}
                >
                  <img src={assetUrl(candidate.url)} alt={candidate.name} />
                  {selected && (
                    <span className="comic-candidate-badge">
                      <CheckIcon size={11} /> 최종
                    </span>
                  )}
                </button>
                <div className="comic-candidate-meta">
                  <span>
                    seed {candidate.seed} · {candidate.width}×{candidate.height}
                  </span>
                  <button
                    type="button"
                    className="comic-candidate-delete"
                    onClick={() => onDeleteCandidate(candidate)}
                    title="후보 삭제"
                  >
                    <TrashIcon size={11} />
                  </button>
                </div>
              </div>
            );
          })}
          {picking && <span className="spinner" />}
        </div>
      ) : (
        <p className="setting-note">아직 후보가 없습니다. 「후보 그리기」를 누르세요.</p>
      )}

      <details className="comic-cut-prompt">
        <summary>프롬프트 보기</summary>
        <p>
          <strong>+</strong> {cut.prompt}
        </p>
        <p>
          <strong>−</strong> {cut.negative}
        </p>
      </details>
    </article>
  );
}
