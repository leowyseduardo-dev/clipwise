from __future__ import annotations

import logging
import os
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from . import db, meter
from .audio_analysis import analyze_audio
from .config import settings
from .sources import REMOTE_SOURCES
from .context import (
    enrich_source_meta,
    merge_source_meta,
    source_meta_from_info,
    source_meta_from_upload,
)
from .ingest import (
    download_source_section,
    download_source_video,
    fetch_source_audio,
    fetch_source_info,
    find_existing_source,
    inspect_source,
    prepare_working_copy,
)
from .moments import generate_moments
from .render import cleanup_old_outputs, render_clip
from .scenes import detect_scenes
from .transcribe import release_idle_model, transcribe
from .utils import CancelledError, MediaError, extract_audio, has_render_headroom, probe_media
from .visual_analysis import analyze_visual

logger = logging.getLogger(__name__)


def _cancelled(job_id: str) -> bool:
    job = db.get_job(job_id)
    return job is None or job["status"] == "cancelled"


def _fail_open_clips(job_id: str, message: str) -> None:
    for clip in db.list_clips(job_id):
        if clip["status"] in {"queued", "rendering"}:
            db.update_clip(clip["id"], status="failed", error=message[:500])


def _mark_rerendered_job_ready(job_id: str) -> None:
    """Close a failed job once every one of its clips has rendered."""
    job = db.get_job(job_id)
    if job is None or job["status"] not in {"failed", "cancelled"}:
        return
    clips = db.list_clips(job_id)
    if not clips or any(clip["status"] != "ready" for clip in clips):
        return
    db.update_job(job_id, status="ready", stage="done", progress=100, error=None)


def _progress_writer(job_id: str) -> Callable[[float, str | None], None]:
    state = {"value": -1.0, "stage": "", "time": 0.0}

    def update(value: float, stage: str | None = None) -> None:
        now = time.monotonic()
        value = round(max(0.0, min(100.0, value)), 1)
        if (
            (stage is None or stage == state["stage"])
            and abs(value - state["value"]) < 0.6
            and now - state["time"] < 0.9
        ):
            return
        fields: dict[str, Any] = {"progress": value}
        if stage and stage != state["stage"]:
            fields["stage"] = stage
        try:
            db.update_job(job_id, **fields)
        except Exception:  # job could have been deleted from another request
            return
        state["value"] = value
        state["time"] = now
        if stage:
            state["stage"] = stage

    return update


def _source_path(job: dict[str, Any], workdir: Path) -> Path:
    source_file = job.get("source_file")
    if source_file:
        candidate = (workdir / source_file).resolve()
        if candidate.exists():
            return candidate
    working = workdir / "working.mp4"
    if working.exists():
        return working
    raise MediaError("No se encuentra el archivo de video del trabajo.")


def _music_path(job: dict[str, Any], workdir: Path) -> Path | None:
    music_file = job.get("music_file")
    if not music_file:
        return None
    candidate = workdir / music_file
    return candidate if candidate.exists() else None


_MB = 1024 * 1024


def _require_free_space(path: Path, required_bytes: int, label: str) -> None:
    free = shutil.disk_usage(path).free
    if free < required_bytes:
        raise MediaError(
            f"No hay suficiente espacio libre para {label}: se necesitan "
            f"~{required_bytes / (1024 ** 3):.1f} GB y quedan "
            f"{free / (1024 ** 3):.1f} GB. Libera espacio y reintenta."
        )


def _options(job: dict[str, Any]) -> dict[str, Any]:
    options = {
        "subtitle_style": settings.default_subtitle_style,
        "remove_silences": True,
        "dynamic_zoom": True,
        "max_clips": None,
        "language": None,
        "layout": "auto",
        "context_overlay": True,
        "title_card": "",
        "title_card_seconds": 4.0,
        "title_card_position": "top",
        "title_card_style": "impact",
    }
    options.update(job.get("options") or {})
    return options


def _render_options(options: dict[str, Any]) -> dict[str, Any]:
    return {
        **{key: options[key] for key in ("aspect", "caption_font", "caption_color", "accent_color", "music_level", "saturation", "brand_text", "logo_id", "transition", "platform", "sound_accent") if key in options},
        "remove_silences": bool(options.get("remove_silences", True)),
        "dynamic_zoom": bool(options.get("dynamic_zoom", True)),
        "layout": str(options.get("layout") or "auto"),
        "context_overlay": bool(options.get("context_overlay", True)),
        "title_card": str(options.get("title_card") or "")[:120],
        "title_card_seconds": float(options.get("title_card_seconds") or 4.0),
        "title_card_position": str(options.get("title_card_position") or "top"),
        "title_card_style": str(options.get("title_card_style") or "impact"),
    }


def _section_clip(clip: dict[str, Any]) -> dict[str, Any]:
    duration = max(0.2, float(clip["end"]) - float(clip["start"]))
    return {**clip, "start": 0.0, "end": duration}


def _ensure_clip_section(
    job: dict[str, Any],
    clip: dict[str, Any],
    workdir: Path,
    *,
    info: dict[str, Any] | None = None,
    used_auth: dict[str, Any] | None = None,
    on_progress: Callable[[float], None] | None = None,
) -> Path:
    """Return a local clip-sized file, downloading only that window."""
    clip_dir = workdir / "clips" / str(clip["id"])
    section = clip_dir / "section.mp4"
    if section.exists() and section.stat().st_size > 1024:
        try:
            probe_media(section)
            return section
        except MediaError:
            section.unlink(missing_ok=True)

    url = job.get("source_url")
    if not url:
        raise MediaError("Este clip necesita el enlace original del video.")
    if info is None or used_auth is None:
        info, used_auth = fetch_source_info(url)
    start = max(0.0, float(clip["start"]))
    end = float(clip["end"]) + 0.5
    total = float(info.get("duration") or end)
    section_seconds = max(1.0, min(end, total) - start)
    _require_free_space(
        workdir,
        max(128 * _MB, int(section_seconds * 500_000)),
        f"descargar la seccion del clip {clip['id'][:8]}",
    )
    return download_source_section(
        url,
        workdir,
        info,
        used_auth,
        start,
        end,
        section,
        on_progress=on_progress,
    )


def process_job(job_id: str) -> None:
    with meter.measuring(job_id):
        _process_job(job_id)


def _process_job(job_id: str) -> None:
    job = db.get_job(job_id)
    if not job:
        return
    if job["status"] == "cancelled":
        return

    workdir = settings.jobs_dir / job_id
    workdir.mkdir(parents=True, exist_ok=True)
    options = _options(job)
    started = time.monotonic()
    progress = _progress_writer(job_id)
    db.update_job(job_id, status="processing", stage="preparing", progress=1, error=None)

    try:
        source: Path
        title = job["title"]
        meta = dict(job.get("meta") or {})
        long_mode = False
        prepared: dict[str, Any]
        source_info: dict[str, Any] | None = None
        source_auth: dict[str, Any] = {}

        if job["source_type"] in REMOTE_SOURCES:
            progress(2, "downloading")
            url = job["source_url"] or ""
            source_info, source_auth = fetch_source_info(url)
            meta = merge_source_meta(meta, source_meta_from_info(source_info))
            title = str(
                meta.get("source_title") or meta.get("title") or "Video importado"
            )[:200]
            source_duration = float(source_info.get("duration") or 0)
            long_mode = source_duration > settings.long_source_seconds
            db.update_job(
                job_id,
                title=title,
                duration=round(source_duration, 3),
                meta_json=meta,
            )

            if long_mode:
                logger.info(
                    "Fuente larga (%.1f min): se descarga solo el audio.",
                    source_duration / 60.0,
                )
                _require_free_space(
                    workdir,
                    max(512 * _MB, int(source_duration * 30_000)),
                    "descargar el audio de la transmision larga",
                )
                source, source_info, source_auth = fetch_source_audio(
                    url,
                    workdir,
                    on_progress=lambda value: progress(
                        2 + value * 0.04, "downloading"
                    ),
                    info=source_info,
                    used_auth=source_auth,
                )
                db.update_job(job_id, source_file=source.name)
                working = source
                prepared = {
                    "duration": source_duration,
                    "width": int(source_info.get("width") or 1920),
                    "height": int(source_info.get("height") or 1080),
                    "fps": float(source_info.get("fps") or 30.0),
                    "has_audio": True,
                    "video_codec": "h264",
                    "rotation": 0,
                    "container": source.suffix.lower().lstrip("."),
                }
                meta["long_mode"] = True
                meta["video_info"] = {
                    "width": prepared["width"],
                    "height": prepared["height"],
                    "fps": prepared["fps"],
                }
                db.update_job(job_id, meta_json=meta)
            else:
                existing = find_existing_source(workdir, source_duration)
                if existing is not None:
                    logger.info(
                        "Fuente completa ya en el trabajo; se reutiliza %s",
                        existing.name,
                    )
                    source = existing
                else:
                    # The merged download plus its merge temp file coexist on
                    # disk: budget ~900 KB/s so a 3.5-hour stream that really
                    # weighs 3 GB + 3 GB temp fails early with a clear message
                    # instead of filling the drive to zero bytes and crashing
                    # the whole app mid-merge.
                    _require_free_space(
                        workdir,
                        max(512 * _MB, int(source_duration * 900_000)),
                        "descargar el video completo",
                    )
                    source = download_source_video(
                        url,
                        workdir,
                        source_info,
                        source_auth,
                        on_progress=lambda value: progress(
                            2 + value * 0.06, "downloading"
                        ),
                    )
                db.update_job(job_id, source_file=source.name)
                progress(9, "preparing")
                info = inspect_source(source)
                working, prepared = prepare_working_copy(
                    source,
                    workdir,
                    info,
                    on_progress=lambda value: progress(
                        9 + value * 0.02, "preparing"
                    ),
                )
                db.update_job(
                    job_id,
                    source_file=working.name,
                    duration=round(float(prepared["duration"]), 3),
                    title=title,
                )
        else:
            if not job.get("source_file"):
                raise MediaError("El trabajo no tiene archivo de origen.")
            source = workdir / job["source_file"]
            info = inspect_source(source)
            if not meta.get("source_title"):
                meta["source_title"] = title
            meta = merge_source_meta(
                meta,
                source_meta_from_upload(
                    title=title,
                    filename=source.name,
                    streamer=str(meta.get("streamer") or ""),
                    game=str(meta.get("game") or ""),
                ),
            )
            db.update_job(
                job_id,
                duration=round(float(info["duration"]), 3),
                meta_json=meta,
            )
            progress(9, "preparing")
            working, prepared = prepare_working_copy(
                source,
                workdir,
                info,
                on_progress=lambda value: progress(9 + value * 0.02, "preparing"),
            )
            db.update_job(
                job_id,
                source_file=working.name,
                duration=round(float(prepared["duration"]), 3),
                title=title,
            )

        if _cancelled(job_id):
            raise CancelledError("Trabajo cancelado.")

        duration = float(prepared["duration"])
        progress(12, "extracting_audio")
        transcript: dict[str, Any] = {"segments": [], "language": ""}
        voices = []
        audio_features: dict[str, Any] | None = None
        audio_path = workdir / "audio.flac"
        if prepared["has_audio"]:
            if not audio_path.exists() or audio_path.stat().st_size == 0:
                extract_audio(working, audio_path)
            if settings.audio_analysis:
                progress(13, "analyzing_audio")
                try:
                    audio_features = analyze_audio(audio_path, duration=duration)
                except Exception as exc:
                    logger.warning("Analisis de audio fallido: %s", exc)
            progress(14, "transcribing")
            try:
                transcript = transcribe(
                    audio_path,
                    duration,
                    language=options.get("language") or None,
                    on_progress=lambda value: progress(
                        14 + value * 0.40, "transcribing"
                    ),
                    checkpoint_dir=workdir,
                )
                try:
                    from .diarization import speaker_turns
                    voices = speaker_turns(audio_path, transcript.get("segments") or [])
                except Exception:
                    logger.warning("No se pudo estimar las voces; se conserva la transcripción.", exc_info=True)
            except Exception as exc:
                logger.warning("Transcripcion fallida, se continua sin voz: %s", exc)
            finally:
                release_idle_model()
                # The compressed FLAC is only needed for transcription and
                # signal analysis. Keeping it around during a 10-hour render
                # wastes the disk the render itself needs.
                audio_path.unlink(missing_ok=True)
                if long_mode and source.exists():
                    # Clip sections are downloaded per clip, so the long audio
                    # file is dead weight after the transcript exists.
                    try:
                        source.unlink()
                    except OSError:
                        logger.debug("No se pudo borrar el audio largo.", exc_info=True)
        language = transcript.get("language") or None
        if language:
            db.update_job(job_id, language=language)

        if _cancelled(job_id):
            raise CancelledError("Trabajo cancelado.")

        transcript_text = " ".join(
            str(segment.get("text") or "")
            for segment in (transcript.get("segments") or [])
        )
        meta = enrich_source_meta(meta, transcript_text)
        db.update_job(job_id, meta_json=meta)

        visual_features: dict[str, Any] | None = None
        if long_mode:
            scenes: list[dict[str, float]] = []
        else:
            if settings.visual_analysis:
                progress(55, "analyzing_visual")
                try:
                    visual_features = analyze_visual(
                        working,
                        duration=duration,
                    )
                except Exception as exc:
                    logger.warning("Analisis visual fallido: %s", exc)
            sampled_scenes = (visual_features or {}).get("scenes")
            if sampled_scenes is None:
                progress(57, "detecting_scenes")
                scenes = detect_scenes(working, duration=duration)
            else:
                scenes = sampled_scenes
        analysis_modes = ["transcript"] if transcript.get("segments") else []
        if voices:
            analysis_modes.append("speaker_turns")
            options["speaker_turns"] = voices
        if audio_features:
            analysis_modes.append("audio")
        if visual_features:
            analysis_modes.append("visual")
        meta["analysis_modes"] = analysis_modes
        db.update_job(job_id, meta_json=meta)

        if options.get("use_creator_profile"):
            from .studio import profile_for
            options["creator_profile"] = profile_for(meta.get("creator_id") or "local")
            options["subtitle_style"] = options["creator_profile"].get("style") or options["subtitle_style"]
        progress(60, "analyzing_moments")
        moments = generate_moments(
            transcript.get("segments") or [],
            scenes,
            duration=duration,
            options=SimpleNamespace(**options),
            requested=options.get("max_clips"),
            language=language,
            meta=meta,
            audio_features=audio_features,
            visual_features=visual_features,
        )
        progress(68, "creating_clips")

        clip_ids: list[str] = []
        style = str(options["subtitle_style"])
        for index, moment in enumerate(moments):
            clip = db.add_clip(
                clip_id=f"{job_id[:8]}{index:02d}{_random_suffix()}",
                job_id=job_id,
                idx=index,
                start=float(moment["start"]),
                end=float(moment["end"]),
                duration=float(moment["duration"]),
                score=int(moment["score"]),
                score_breakdown=moment["score_breakdown"],
                category=str(moment.get("category") or ""),
                title=str(moment["title"]),
                hook=str(moment["hook"]),
                reason=str(moment["reason"]),
                caption=str(moment["caption"]),
                description=str(moment.get("description") or ""),
                tags=list(moment["tags"]),
                subtitles=moment["subtitles"],
                style=style,
                status="queued",
                overlay={**(moment.get("overlay") or {}), "render_options": _render_options(options),
                         "voices": [v for v in voices if v["end"]>moment["start"] and v["start"]<moment["end"]]},
            )
            clip_ids.append(clip["id"])

        db.update_job(
            job_id,
            clips_target=len(clip_ids),
            progress=70,
            stage="rendering",
        )
        music = _music_path(job, workdir)
        render_options = _render_options(options)
        total = max(1, len(clip_ids))
        fractions = [0.0] * len(clip_ids)
        progress_lock = threading.Lock()

        def clip_progress(index: int, value: float, stage: str = "rendering") -> None:
            with progress_lock:
                fractions[index] = max(fractions[index], min(1.0, value))
                progress(70 + sum(fractions) / total * 29, stage)

        def render_one(index: int, clip_id: str) -> bool:
            if _cancelled(job_id):
                raise CancelledError("Trabajo cancelado.")
            clip = db.get_clip(clip_id)
            if not clip:
                clip_progress(index, 1.0)
                return False
            db.update_clip(clip_id, status="rendering", error=None)
            try:
                if long_mode:
                    clip_progress(index, 0, "downloading_clip")
                    section = _ensure_clip_section(
                        job,
                        clip,
                        workdir,
                        info=source_info,
                        used_auth=source_auth,
                        on_progress=lambda value: clip_progress(
                            index, value / 100.0 * 0.18, "downloading_clip"
                        ),
                    )
                    render_source = section
                    render_clip_data = _section_clip(clip)
                else:
                    render_source = working
                    render_clip_data = clip
                render_started = time.monotonic()
                result = render_clip(
                    source=render_source,
                    clip=render_clip_data,
                    options=render_options,
                    music_path=music,
                    clip_dir=workdir / "clips" / clip_id,
                    progress=lambda value: clip_progress(
                        index,
                        (0.18 if long_mode else 0.0)
                        + value / 100.0 * (0.82 if long_mode else 1.0),
                    ),
                    is_cancelled=lambda: _cancelled(job_id),
                )
                meter.record("render", job_id=job_id, seconds=time.monotonic()-render_started)
                db.update_clip(
                    clip_id,
                    status="ready",
                    duration=result["duration"],
                    video_file=result["video"].relative_to(workdir).as_posix(),
                    thumb_file=result["thumb"].relative_to(workdir).as_posix(),
                    error=None,
                )
                cleanup_old_outputs(
                    workdir / "clips" / clip_id,
                    keep={result["video"], result["thumb"]},
                )
                if long_mode:
                    (workdir / "clips" / clip_id / "section.mp4").unlink(
                        missing_ok=True
                    )
                return True
            except CancelledError:
                raise
            except Exception as exc:
                logger.exception("Fallo el render del clip %s", clip_id)
                db.update_clip(clip_id, status="failed", error=str(exc)[:500])
                return False
            finally:
                clip_progress(index, 1.0)

        rendered = 0
        # Two encoders improved a two-clip 1080x1920 benchmark on the bundled
        # 2-core/4-thread target. Limit concurrency to avoid memory pressure.
        workers = 2 if len(clip_ids) > 1 and (os.cpu_count() or 1) >= 4 and has_render_headroom() else 1
        if workers == 1:
            for index, clip_id in enumerate(clip_ids):
                rendered += int(render_one(index, clip_id))
        else:
            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="Clipwise-render") as pool:
                futures = [
                    pool.submit(render_one, index, clip_id)
                    for index, clip_id in enumerate(clip_ids)
                ]
                for future in as_completed(futures):
                    try:
                        rendered += int(future.result())
                    except CancelledError:
                        for pending in futures:
                            pending.cancel()
                        raise

        if rendered == 0:
            raise MediaError("Ningun clip pudo renderizarse. Revisa el video de origen.")

        if _cancelled(job_id):
            raise CancelledError("Trabajo cancelado.")
        db.update_job(
            job_id,
            status="ready",
            meta_json={**meta,"processing_seconds":round(time.monotonic()-started,2)},
            stage="done",
            progress=100,
            error=None,
            clips_target=len(clip_ids),
        )
        logger.info("Trabajo %s completado con %d clips.", job_id, rendered)
    except CancelledError:
        db.update_job(job_id, status="cancelled", stage="cancelled", error=None)
        _fail_open_clips(job_id, "Trabajo cancelado.")
    except Exception as exc:
        logger.exception("El trabajo %s fallo.", job_id)
        message = str(exc) or exc.__class__.__name__
        db.update_job(job_id, status="failed", stage="", error=message[:1200])
        _fail_open_clips(job_id, message)


def process_clip_render(clip_id: str) -> None:
    clip = db.get_clip(clip_id)
    if not clip:
        return
    job = db.get_job(clip["job_id"])
    if not job:
        return
    workdir = settings.jobs_dir / job["id"]
    long_mode = bool((job.get("meta") or {}).get("long_mode"))
    try:
        if long_mode:
            source = _ensure_clip_section(job, clip, workdir)
            render_clip_data = _section_clip(clip)
        else:
            source = _source_path(job, workdir)
            render_clip_data = clip
    except Exception as exc:
        db.update_clip(clip_id, status="failed", error=str(exc)[:500])
        return

    options = _options(job)
    render_options = _render_options(options)
    render_options.update((clip.get("overlay") or {}).get("render_options") or {})
    db.update_clip(clip_id, status="rendering", error=None)
    try:
        render_started = time.monotonic()
        result = render_clip(
            source=source,
            clip=render_clip_data,
            options=render_options,
            music_path=_music_path(job, workdir),
            clip_dir=workdir / "clips" / clip_id,
        )
        meter.record("render", job_id=job["id"], seconds=time.monotonic()-render_started)
        db.update_clip(
            clip_id,
            status="ready",
            duration=result["duration"],
            video_file=result["video"].relative_to(workdir).as_posix(),
            thumb_file=result["thumb"].relative_to(workdir).as_posix(),
            error=None,
        )
        cleanup_old_outputs(
            workdir / "clips" / clip_id,
            keep={result["video"], result["thumb"]},
        )
        if long_mode:
            (workdir / "clips" / clip_id / "section.mp4").unlink(missing_ok=True)
        _mark_rerendered_job_ready(clip["job_id"])
    except Exception as exc:
        logger.exception("Fallo el re-render del clip %s", clip_id)
        db.update_clip(clip_id, status="failed", error=str(exc)[:500])


def _random_suffix() -> str:
    import uuid

    return uuid.uuid4().hex[:12]
