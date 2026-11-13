"""Build a local, uncensored copy of the installed nk comic kit.

The original nk installation is never modified.  This script copies the nk
runtime files into ``nk_uncensored/`` (gitignored) and removes the ``safe``
rating tag from the prompt builders.  Character files, drawing workflows,
fonts, docs and episodes are shared with the original kit through directory
junctions so existing comics keep working.

Usage:
    python scripts/patch_nk_uncensored.py [--source C:\\nk] [--dest ...]

Required Notice: Copyright (c) 2026 니코(Niko)
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = Path(r"C:\nk")
DEFAULT_DEST = ROOT / "nk_uncensored"

COPY_FILES = (
    "nk.py",
    "nk_animacut.py",
    "nk_animafix.py",
    "nk_animeseg.py",
    "nk_animatest.py",
    "nk_auto.py",
    "nk_backfix.py",
    "nk_charadd.py",
    "nk_compose.py",
    "nk_cover.py",
    "nk_detail.py",
    "nk_duosplit.py",
    "nk_easy.py",
    "nk_edit.py",
    "nk_editcmd.py",
    "nk_facefix.py",
    "nk_fetch.py",
    "nk_flow.py",
    "nk_guide.md",
    "nk_handfix.py",
    "nk_headcheck.py",
    "nk_inspect.py",
    "nk_joint.py",
    "nk_layer.py",
    "nk_layout2.py",
    "nk_letter2.py",
    "nk_lines.py",
    "nk_lorablock.py",
    "nk_partfix.py",
    "nk_plan.py",
    "nk_pose.py",
    "nk_pose3d_auto.py",
    "nk_propfix.py",
    "nk_refine.py",
    "nk_regional.py",
    "nk_regionlora.py",
    "nk_restyle.py",
    "nk_sam.py",
    "nk_story.py",
    "nk_styleref.py",
    "nk_tagger.py",
    "nk_train.py",
    "nk_trainanima.py",
    "nk_trainmask.py",
    "nk_web.py",
    "nk_webtoon.py",
    "presets.yaml",
    "cover.yaml",
    "duosplit_settings.yaml",
    "nk.bat",
)

JUNCTION_DIRS = (
    "characters",
    "workflows",
    "fonts",
    "docs",
    "concepts",
    "tools",
    "episodes",
)

SAFE_REPLACEMENTS: dict[str, list[tuple[str, str]]] = {
    "nk.py": [
        ('    rating = "safe"                  # ', '    rating = "nsfw"                  # '),
        ('    pos.append("safe")\n', '    # safe tag removed for the uncensored local runtime\n'),
    ],
    "nk_animacut.py": [
        ('"masterpiece, best quality, score_7, safe"', '"masterpiece, best quality, score_7"'),
    ],
    "nk_animafix.py": [
        ('"masterpiece, best quality, score_7, safe"', '"masterpiece, best quality, score_7"'),
    ],
    "nk_partfix.py": [
        ('["masterpiece, best quality, score_7, safe"]', '["masterpiece, best quality, score_7"]'),
    ],
    "nk_regionlora.py": [
        ('"masterpiece, best quality, score_7, safe"', '"masterpiece, best quality, score_7"'),
    ],
    "nk_duosplit.py": [
        ('"masterpiece, best quality, score_7, safe"', '"masterpiece, best quality, score_7"'),
    ],
    "nk_webtoon.py": [
        ('"masterpiece, best quality, score_7, safe, " + boys', '"masterpiece, best quality, score_7, " + boys'),
        ('"masterpiece, best quality, score_7, safe, no humans, ', '"masterpiece, best quality, score_7, no humans, '),
        ('"masterpiece, best quality, score_7, safe, " + ("1boy, "', '"masterpiece, best quality, score_7, " + ("1boy, "'),
        ('nk.qa_folder(folder, c2, qa_cfg, "safe", files=[f])', 'nk.qa_folder(folder, c2, qa_cfg, "nsfw", files=[f])'),
    ],
    "nk_flow.py": [
        ('pos = "%quality%, %artist%, safe, %char%, %scene%"', 'pos = "%quality%, %artist%, %char%, %scene%"'),
    ],
}


def _run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(cmd)}\n{result.stdout}\n{result.stderr}")


def _junction(link: Path, target: Path) -> None:
    if link.exists() or link.is_symlink():
        return
    if os.name != "nt":
        link.symlink_to(target, target_is_directory=True)
        return
    _run(["cmd", "/c", "mklink", "/J", str(link), str(target)])


def _copy_runtime(source: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for name in COPY_FILES:
        src = source / name
        if not src.is_file():
            print(f"[skip] {name} (not found)")
            continue
        shutil.copy2(src, dest / name)
    agreed = source / ".nk_agreed"
    if agreed.is_file():
        shutil.copy2(agreed, dest / ".nk_agreed")
    for name in JUNCTION_DIRS:
        target = source / name
        if target.is_dir():
            _junction(dest / name, target)
    (dest / "_remote").mkdir(exist_ok=True)
    (dest / "runs").mkdir(exist_ok=True)
    (dest / "NOTICE.txt").write_text(
        "This folder is a local patch copy of the nk comic kit.\n"
        "The original installation was not modified.\n\n"
        "Required Notice: Copyright (c) 2026 니코(Niko)\n",
        encoding="utf-8",
    )


def _patch_safe(dest: Path) -> list[str]:
    changed: list[str] = []
    for name, replacements in SAFE_REPLACEMENTS.items():
        path = dest / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        before = text
        for old, new in replacements:
            if old not in text:
                continue
            text = text.replace(old, new)
        if text != before:
            path.write_text(text, encoding="utf-8", newline="\n")
            changed.append(name)
    return changed


def _validate(dest: Path) -> None:
    for path in sorted(dest.glob("*.py")):
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(path)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"py_compile failed for {path.name}\n{result.stderr}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    args = parser.parse_args()

    source = args.source.expanduser().resolve()
    dest = args.dest.expanduser().resolve()
    if not (source / "nk.py").is_file():
        print(f"nk.py not found in {source}", file=sys.stderr)
        return 1

    print(f"[1/4] copying runtime: {source} -> {dest}")
    _copy_runtime(source, dest)
    print("[2/4] removing safe tags from prompt builders")
    changed = _patch_safe(dest)
    print("      patched: " + (", ".join(changed) if changed else "already clean"))
    print("[3/4] validating python files")
    _validate(dest)
    print("[4/4] done")
    print(f"      runtime: {dest}")
    print("      original nk was not modified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
