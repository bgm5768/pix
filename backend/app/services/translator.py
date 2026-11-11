"""Offline Korean -> English prompt translation.

The image generator sends prompts to SDXL, which only understands English well.
This module runs the quantized ONNX build of Helsinki-NLP/opus-mt-ko-en
(published by Xenova) on the CPU, so translation works without PyTorch, a
network connection, or a local LLM.

Only text that actually contains Hangul is translated. English prompts are
returned untouched because Marian would otherwise "translate" them and damage
perfectly good prompt wording.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

from app.config import TranslationConfig

logger = logging.getLogger("pixelforge.translate")

_KOREAN_RE = re.compile(r"[\uac00-\ud7a3\u3131-\u318e]")
_SPACE_RE = re.compile(r"\s+")
_SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([,.;:!?])")
_TRAILING_PERIOD_RE = re.compile(r"\.\s*$")
_WOODS_RE = re.compile(r"\b(through|in|into) the woods\b", re.IGNORECASE)
# Split at sentence boundaries while keeping the punctuation with the sentence.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?。？！;])\s+|\n+")
# Fallback split for a single very long sentence.
_CLAUSE_SPLIT_RE = re.compile(r"(?<=[,，、])\s*")
# Prompt terms are usually comma-separated. English terms between Korean ones
# must be preserved instead of being fed to Marian.
_PROMPT_SPLIT_RE = re.compile(r"\s*[,;\n]\s*")
_MAX_CHUNK_CHARS = 360


@dataclass(frozen=True)
class TranslationResult:
    source: str
    text: str
    translated: bool
    model: str = "opus-mt-ko-en"
    elapsed_ms: int = 0
    error: str | None = None


class Translator:
    """Lazy, thread-safe wrapper around the quantized Marian ONNX model."""

    def __init__(self, config: TranslationConfig, model_dir: Path):
        self.config = config
        self.model_dir = Path(model_dir)
        self._lock = threading.Lock()
        self._cache_lock = threading.Lock()
        self._cache: OrderedDict[tuple[str, int], TranslationResult] = OrderedDict()
        self._loaded = False
        self._load_error: str | None = None
        self._tokenizer = None
        self._encoder = None
        self._decoder = None
        self._np = None
        self._model_config: dict[str, object] = {}

    @property
    def enabled(self) -> bool:
        return bool(self.config.enabled)

    @property
    def load_error(self) -> str | None:
        return self._load_error

    @property
    def available(self) -> bool:
        return self.enabled and self.model_dir.joinpath(
            "onnx", "encoder_model_quantized.onnx"
        ).exists()

    @staticmethod
    def is_korean(text: str) -> bool:
        return bool(_KOREAN_RE.search(text or ""))

    def translate(self, text: str, max_new_tokens: int | None = None) -> TranslationResult:
        """Translate ``text`` to English.

        Returns the original text unchanged (``translated=False``) when the
        input is empty, already English, translation is disabled, or the model
        cannot be loaded.
        """
        source = (text or "").strip()
        if not source:
            return TranslationResult(source="", text="", translated=False)
        if not self.is_korean(source):
            return TranslationResult(source=source, text=source, translated=False)
        if not self.enabled:
            return TranslationResult(source=source, text=source, translated=False)

        limit = max(16, int(max_new_tokens or self.config.max_new_tokens))
        cache_key = (source, limit)
        with self._cache_lock:
            cached = self._cache.get(cache_key)
            if cached is not None:
                self._cache.move_to_end(cache_key)
                return cached

        started = time.perf_counter()
        try:
            translated = self._translate_prompt(source, limit)
        except Exception as exc:
            message = f"번역 모델을 실행하지 못했습니다: {exc}"
            logger.warning("Translation failed: %s", exc, exc_info=True)
            return TranslationResult(
                source=source,
                text=source,
                translated=False,
                elapsed_ms=int((time.perf_counter() - started) * 1000),
                error=message,
            )

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        result = TranslationResult(
            source=source,
            text=translated,
            translated=bool(translated) and translated != source,
            elapsed_ms=elapsed_ms,
            error=self._load_error,
        )
        if result.text:
            with self._cache_lock:
                self._cache[cache_key] = result
                while len(self._cache) > max(1, int(self.config.cache_size)):
                    self._cache.popitem(last=False)
        return result

    # ------------------------------------------------------------------
    # Lazy model loading
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            if not self.config.enabled:
                raise RuntimeError("번역 기능이 설정에서 꺼져 있습니다.")
            encoder_path = self.model_dir / "onnx" / "encoder_model_quantized.onnx"
            decoder_path = self.model_dir / "onnx" / "decoder_model_quantized.onnx"
            config_path = self.model_dir / "config.json"
            for path in (encoder_path, decoder_path, config_path):
                if not path.exists():
                    raise FileNotFoundError(
                        f"번역 모델 파일이 없습니다: {path}. "
                        "scripts/download_translation_model.bat을 실행해 주세요."
                    )

            # Imported lazily so the backend still starts when the optional
            # translation dependencies are missing.
            import numpy as np
            import onnxruntime as ort
            from transformers import MarianTokenizer

            self._model_config = json.loads(config_path.read_text(encoding="utf-8"))
            tokenizer = MarianTokenizer.from_pretrained(
                str(self.model_dir), local_files_only=True
            )
            options = ort.SessionOptions()
            # Keep the CPU footprint modest: translation must not stall the
            # ComfyUI polling loop or make the UI feel unresponsive.
            options.intra_op_num_threads = 4
            options.inter_op_num_threads = 1
            encoder = ort.InferenceSession(
                str(encoder_path),
                sess_options=options,
                providers=["CPUExecutionProvider"],
            )
            decoder = ort.InferenceSession(
                str(decoder_path),
                sess_options=options,
                providers=["CPUExecutionProvider"],
            )
            self._np = np
            self._tokenizer = tokenizer
            self._encoder = encoder
            self._decoder = decoder
            self._loaded = True
            self._load_error = None
            logger.info(
                "Translation model loaded: %s (vocab=%s)",
                self.model_dir,
                len(tokenizer),
            )

    def _translate_prompt(self, text: str, limit: int) -> str:
        """Translate only the Korean terms, preserving English prompt terms.

        Image prompts commonly mix a Korean subject with English style words
        (``숲속을 달리는 호랑이, cinematic lighting``). Marian would mangle those
        English terms, so translate comma-separated segments individually and
        leave segments without Hangul untouched.
        """
        outputs: list[str] = []
        for segment in _PROMPT_SPLIT_RE.split(text):
            segment = segment.strip()
            if not segment:
                continue
            if self.is_korean(segment):
                translated = self._translate_chunks(segment, limit)
                outputs.append(translated or segment)
            else:
                outputs.append(segment)
        return self._clean(", ".join(outputs))

    def _translate_chunks(self, text: str, limit: int) -> str:
        self._load()
        chunks = self._split_text(text)
        outputs: list[str] = []
        for chunk in chunks:
            translated = self._translate_chunk(chunk, limit)
            if translated:
                outputs.append(translated)
        return self._clean(" ".join(outputs))

    def _translate_chunk(self, text: str, limit: int) -> str:
        np = self._np
        tokenizer = self._tokenizer
        encoder = self._encoder
        decoder = self._decoder
        if np is None or tokenizer is None or encoder is None or decoder is None:
            raise RuntimeError("번역 모델이 초기화되지 않았습니다.")

        config = self._model_config
        decoder_start_id = int(config.get("decoder_start_token_id") or 65000)
        eos_id = int(config.get("eos_token_id") or 0)
        pad_id = int(config.get("pad_token_id") or decoder_start_id)
        max_positions = int(config.get("max_position_embeddings") or 512)

        input_ids = list(tokenizer(text)["input_ids"])
        if not input_ids or input_ids[-1] != eos_id:
            input_ids.append(eos_id)
        if len(input_ids) > max_positions:
            input_ids = input_ids[: max_positions - 1] + [eos_id]

        encoder_ids = np.array([input_ids], dtype=np.int64)
        attention_mask = np.ones_like(encoder_ids)
        hidden = encoder.run(
            None,
            {"input_ids": encoder_ids, "attention_mask": attention_mask},
        )[0]

        output_ids = [decoder_start_id]
        # Marian output length is usually close to the source length; this cap
        # prevents a runaway decode on a malformed prompt.
        token_limit = max(16, min(limit, len(input_ids) * 2 + 16))
        repeats = 0
        previous = -1
        for _ in range(token_limit):
            feeds = {
                "input_ids": np.array([output_ids], dtype=np.int64),
                "encoder_attention_mask": attention_mask,
                "encoder_hidden_states": hidden,
            }
            logits = decoder.run(None, feeds)[0]
            scores = logits[0, -1]
            # The pad token doubles as the decoder start token; it must never
            # be emitted as a regular token.
            if 0 <= pad_id < scores.shape[0]:
                scores[pad_id] = -float("inf")
            next_id = int(np.argmax(scores))
            if next_id == eos_id:
                break
            output_ids.append(next_id)
            repeats = repeats + 1 if next_id == previous else 0
            previous = next_id
            if repeats >= 6:
                # Greedy decode occasionally loops on unusual input.
                break

        return tokenizer.decode(output_ids[1:], skip_special_tokens=True)

    @staticmethod
    def _split_text(text: str) -> list[str]:
        """Split long prompts into pieces that fit Marian's 512-token window."""
        sentences = [part.strip() for part in _SENTENCE_SPLIT_RE.split(text) if part.strip()]
        if not sentences:
            sentences = [text.strip()]
        chunks: list[str] = []
        for sentence in sentences:
            if len(sentence) <= _MAX_CHUNK_CHARS:
                chunks.append(sentence)
                continue
            clauses = [
                part.strip() for part in _CLAUSE_SPLIT_RE.split(sentence) if part.strip()
            ]
            current = ""
            for clause in clauses or [sentence]:
                if len(clause) > _MAX_CHUNK_CHARS:
                    if current:
                        chunks.append(current)
                        current = ""
                    for start in range(0, len(clause), _MAX_CHUNK_CHARS):
                        chunks.append(clause[start : start + _MAX_CHUNK_CHARS])
                    continue
                if current and len(current) + len(clause) + 1 > _MAX_CHUNK_CHARS:
                    chunks.append(current)
                    current = clause
                else:
                    current = f"{current} {clause}".strip()
            if current:
                chunks.append(current)
        return chunks

    @staticmethod
    def _clean(text: str) -> str:
        text = _SPACE_RE.sub(" ", text or "").strip()
        text = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", text)
        # Prefer the prompt-friendly wording used in the UI examples.
        text = _WOODS_RE.sub(r"\1 a forest", text)
        # Marian adds a final period to most short outputs. Prompt examples
        # read better without it ("Tiger", "Black cat").
        text = _TRAILING_PERIOD_RE.sub("", text)
        return text.strip()
