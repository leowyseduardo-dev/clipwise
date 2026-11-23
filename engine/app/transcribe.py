from __future__ import annotations

import hashlib
import json
import os
from uuid import uuid4
import logging
import tempfile
from pathlib import Path
from typing import Any, Callable, Iterator

from .config import settings
from .utils import MediaError, has_render_headroom, probe_media, run_ffmpeg

logger = logging.getLogger(__name__)

_ASR_CHUNK_SECONDS = 420.0

_models: dict[tuple[str, str, str], Any] = {}


def release_idle_model() -> None:
    if not has_render_headroom():
        _models.clear()


class TranscriptionError(Exception):
    pass


def _get_model() -> Any:
    key = (settings.whisper_model, settings.whisper_device, settings.whisper_compute)
    if key not in _models:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise TranscriptionError(
                f"No se pudo importar faster-whisper: {exc}"
            ) from exc
        logger.info(
            "Cargando modelo faster-whisper %s (%s/%s)",
            settings.whisper_model,
            settings.whisper_device,
            settings.whisper_compute,
        )
        try:
            _models[key] = WhisperModel(
                settings.whisper_model,
                device=settings.whisper_device,
                compute_type=settings.whisper_compute,
            )
        except Exception as exc:
            raise TranscriptionError(
                f"No se pudo cargar el modelo Whisper '{settings.whisper_model}': {exc}"
            ) from exc
    return _models[key]


def _fallback_words(text: str, start: float, end: float) -> list[dict[str, Any]]:
    tokens = text.split()
    if not tokens:
        return []
    duration = max(0.25, end - start)
    weights = [len(token) + 1 for token in tokens]
    total = float(sum(weights))
    words: list[dict[str, Any]] = []
    cursor = start
    for token, weight in zip(tokens, weights):
        span = duration * weight / total
        words.append(
            {
                "w": token,
                "start": round(cursor, 3),
                "end": round(cursor + span, 3),
                "p": 0.5,
            }
        )
        cursor += span
    return words


def _transcribe_single(
    model: Any,
    audio_path: Path,
    duration: float,
    *,
    language: str | None,
    offset: float,
    total_duration: float,
    on_progress: Callable[[float], None] | None,
) -> tuple[list[dict[str, Any]], Any]:
    try:
        segments_iter, info = model.transcribe(
            str(audio_path),
            language=language or None,
            beam_size=5,
            word_timestamps=True,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
            condition_on_previous_text=False,
        )
    except Exception as exc:
        raise TranscriptionError(f"La transcripcion fallo: {exc}") from exc

    segments: list[dict[str, Any]] = []
    for segment in segments_iter:
        words: list[dict[str, Any]] = []
        for word in getattr(segment, "words", None) or []:
            token = (word.word or "").strip()
            if not token:
                continue
            try:
                start = float(word.start) + offset
                end = float(word.end) + offset
            except (TypeError, ValueError):
                continue
            words.append(
                {
                    "w": token,
                    "start": round(max(0.0, start), 3),
                    "end": round(max(start + 0.05, end), 3),
                    "p": round(float(getattr(word, "probability", 1.0) or 0.0), 3),
                }
            )
        text = (segment.text or "").strip()
        if not words and text:
            words = _fallback_words(
                text,
                float(segment.start) + offset,
                float(segment.end) + offset,
            )
        if words:
            segments.append(
                {
                    "start": round(float(segment.start) + offset, 3),
                    "end": round(float(segment.end) + offset, 3),
                    "text": text or " ".join(word["w"] for word in words),
                    "words": words,
                }
            )
        if on_progress and total_duration > 0:
            reported = (offset + float(segment.end)) / total_duration * 100.0
            on_progress(min(99.0, max(0.0, reported)))
    return segments, info


def _chunk_audio(
    audio_path: Path,
    duration: float,
    *,
    directory: Path,
    cached_offsets: set[float] | None = None,
) -> Iterator[tuple[Path, float, float]]:
    offset = 0.0
    index = 0
    while offset < duration - 0.05:
        length = min(_ASR_CHUNK_SECONDS, duration - offset)
        target = directory / f"chunk_{index:03d}.wav"
        if cached_offsets and round(offset, 3) in cached_offsets:
            yield target, offset, length
            offset += length
            index += 1
            continue
        try:
            run_ffmpeg(
                [
                    "-y",
                    "-ss",
                    f"{offset:.3f}",
                    "-t",
                    f"{length:.3f}",
                    "-i",
                    str(audio_path),
                    "-vn",
                    "-ac",
                    "1",
                    "-ar",
                    "16000",
                    "-c:a",
                    "pcm_s16le",
                    str(target),
                ],
                timeout=300,
            )
        except MediaError as exc:
            raise TranscriptionError(f"No se pudo cortar el audio para transcribir: {exc}") from exc
        if not target.exists() or target.stat().st_size == 0:
            raise TranscriptionError("No se pudo preparar un fragmento de audio para transcribir.")
        yield target, offset, length
        target.unlink(missing_ok=True)
        offset += length
        index += 1


def _load_checkpoint(path: Path | None) -> dict[float, list[dict[str, Any]]]:
    if path is None or not path.is_file():
        return {}
    done: dict[float, list[dict[str, Any]]] = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            done[round(float(record["offset"]), 3)] = record["segments"]
    except (OSError, ValueError, KeyError, TypeError):
        logger.warning("Checkpoint de transcripcion danado; se re-transcribe todo.")
        return {}
    return done


def transcribe(
    audio_path: Path,
    duration: float,
    *,
    language: str | None = None,
    on_progress: Callable[[float], None] | None = None,
    checkpoint_dir: Path | None = None,
) -> dict[str, Any]:
    total_duration = float(duration or 0.0)
    if total_duration <= 0:
        try:
            total_duration = float(probe_media(audio_path).get("duration") or 0.0)
        except Exception:
            total_duration = 0.0

    cache = checkpoint_dir / "transcript-v2.json" if checkpoint_dir and audio_path.is_file() else None
    identity = None
    if cache:
        with audio_path.open("rb") as audio:
            digest = hashlib.file_digest(audio, "sha256").hexdigest()
        identity = [digest, settings.whisper_model, settings.whisper_compute, language, round(total_duration, 3)]
        try:
            cached = json.loads(cache.read_text(encoding="utf-8"))
            if cached["key"] == identity and isinstance(cached["result"]["segments"], list):
                if on_progress:
                    on_progress(99.0)
                return cached["result"]
        except (OSError, ValueError, KeyError, TypeError):
            pass
    checkpoint_path = None
    if total_duration <= _ASR_CHUNK_SECONDS:
        segments, info = _transcribe_single(
            _get_model(),
            audio_path,
            total_duration,
            language=language,
            offset=0.0,
            total_duration=total_duration,
            on_progress=on_progress,
        )
    else:
        segments: list[dict[str, Any]] = []
        info = None
        checkpoint_path = (
            checkpoint_dir / ("asr-" + hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:20] + ".jsonl" if identity else "asr_checkpoint.jsonl") if checkpoint_dir else None
        )
        done = _load_checkpoint(checkpoint_path)
        resumed = len(done)
        if resumed:
            logger.info(
                "Checkpoint de transcripcion: %d trozos ya listos, se reutilizan.",
                resumed,
            )
        with tempfile.TemporaryDirectory(prefix="Clipwise-asr-") as temp_dir:
            chunks = _chunk_audio(Path(audio_path), total_duration, directory=Path(temp_dir),
                                  cached_offsets=set(done))
            for chunk, offset, length in chunks:
                key = round(offset, 3)
                if key in done:
                    chunk_segments = done[key]
                    if on_progress and total_duration > 0:
                        reported = (offset + length) / total_duration * 100.0
                        on_progress(min(99.0, max(0.0, reported)))
                else:
                    chunk_segments, chunk_info = _transcribe_single(
                        _get_model(),
                        chunk,
                        length,
                        language=language,
                        offset=offset,
                        total_duration=total_duration,
                        on_progress=on_progress,
                    )
                    if info is None:
                        info = chunk_info
                    if checkpoint_path is not None:
                        try:
                            with checkpoint_path.open(
                                "a", encoding="utf-8"
                            ) as handle:
                                handle.write(
                                    json.dumps(
                                        {
                                            "offset": key,
                                            "segments": chunk_segments,
                                        },
                                        ensure_ascii=False,
                                    )
                                    + "\n"
                                )
                        except OSError:
                            logger.warning(
                                "No se pudo escribir el checkpoint de transcripcion."
                            )
                segments.extend(chunk_segments)

    detected_language = str(getattr(info, "language", "") or language or "")
    probability = float(getattr(info, "language_probability", 0.0) or 0.0)
    if on_progress:
        on_progress(99.0)
    if checkpoint_path is not None and checkpoint_path.exists():
        try:
            checkpoint_path.unlink()
        except OSError:
            pass
    result = {
        "language": detected_language,
        "language_probability": round(probability, 3),
        "segments": segments,
    }
    if cache:
        temp = cache.with_suffix("." + uuid4().hex + ".tmp")
        try:
            temp.write_text(json.dumps({"key": identity, "result": result}, ensure_ascii=False), encoding="utf-8")
            os.replace(temp, cache)
        except OSError:
            logger.warning("No se pudo guardar la transcripción en caché.")
        finally:
            temp.unlink(missing_ok=True)
    return result
