# -*- coding: utf-8 -*-
"""Reprocess saved originals and compare with the saved final pixels."""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import get_settings  # noqa: E402
from app.services.postprocess import postprocess_image  # noqa: E402

CASES = [
    ("eef4b0a1483f", 32, 16, "icon"),
    ("42b7eb87222b", 64, 24, "icon"),
    ("c21cab4e379b", 128, 32, "icon"),
    ("db4aba9d8bae", 32, 16, "character"),
    ("58135ada075c", 64, 24, "character"),
    ("f9de35eea7b4", 128, 32, "character"),
    ("16d6db3bb148", 32, 16, "object"),
    ("a87f39939391", 64, 24, "object"),
    ("5a2a9153c779", 128, 32, "object"),
    ("7eb75f6efe71", 32, 16, "object"),
    ("27af2e4b60ab", 64, 24, "object"),
    ("60d3661c1cd9", 128, 32, "object"),
    ("1de36f32f711", 32, 16, "icon"),
    ("2309550fddab", 64, 24, "icon"),
    ("1ae513cad293", 128, 32, "icon"),
    ("c942eec22e73", 64, 16, "icon"),
]

settings = get_settings()
for job_id, size, palette, mode in CASES:
    original = Image.open(ROOT / "outputs" / "originals" / f"{job_id}_original.png").convert("RGB")
    result = postprocess_image(original, size, "quantize", palette, True, settings.generation, mode, "nearest")
    saved_path = ROOT / "outputs" / "pixel_art" / f"{job_id}_pixel_{size}.png"
    saved = Image.open(saved_path)
    result_bytes = result.image.convert("RGBA").tobytes()
    saved_bytes = saved.convert("RGBA").tobytes()
    mask = np.asarray(result.image.convert("RGBA"))[:, :, 3] > 0
    _, components = ndimage.label(mask, structure=np.ones((3, 3), dtype=bool))
    print(
        job_id,
        "identical=" + str(hashlib.sha256(result_bytes).digest() == hashlib.sha256(saved_bytes).digest()),
        f"components={components}",
        f"fill={result.subject_fill:.3f}",
        f"warnings={len(result.warnings)}",
    )
