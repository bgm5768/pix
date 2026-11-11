"""Download the offline Korean -> English translation model.

The backend uses the quantized ONNX build of Helsinki-NLP/opus-mt-ko-en
(published by Xenova).  ``vocab.json`` is not part of that repository, but
``MarianTokenizer`` needs it, so it is fetched from the original
Helsinki-NLP model.
"""

from __future__ import annotations

import shutil
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "models" / "translation" / "opus-mt-ko-en"
XENOVA = "https://huggingface.co/Xenova/opus-mt-ko-en/resolve/main/"
HELSINKI = "https://huggingface.co/Helsinki-NLP/opus-mt-ko-en/resolve/main/"
FILES = [
    (XENOVA, "config.json"),
    (XENOVA, "generation_config.json"),
    (XENOVA, "tokenizer_config.json"),
    (XENOVA, "source.spm"),
    (XENOVA, "target.spm"),
    (HELSINKI, "vocab.json"),
    (XENOVA, "onnx/encoder_model_quantized.onnx"),
    (XENOVA, "onnx/decoder_model_quantized.onnx"),
]


def download(base: str, name: str, force: bool) -> None:
    destination = TARGET / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not force:
        print(f"[skip] {name} ({destination.stat().st_size:,} bytes)")
        return
    url = base + name
    partial = destination.with_suffix(destination.suffix + ".part")
    print(f"[get ] {name}")
    request = urllib.request.Request(url, headers={"User-Agent": "PixelForge-Local/1.0"})
    with urllib.request.urlopen(request, timeout=180) as response:
        with partial.open("wb") as handle:
            shutil.copyfileobj(response, handle, length=1024 * 256)
    partial.replace(destination)
    print(f"[ok  ] {name} ({destination.stat().st_size:,} bytes)")


def main() -> int:
    force = "--force" in sys.argv
    TARGET.mkdir(parents=True, exist_ok=True)
    for base, name in FILES:
        download(base, name, force)
    print(f"\nModel ready: {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
