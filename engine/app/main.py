from __future__ import annotations

import logging
import json
import os
import re
import shutil
import uuid
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask
from starlette.requests import Request

from . import ai, db, jobs, live, publishing, studio
from .config import settings
from .descriptions import build_publication
from .ingest import IngestError, inspect_source, validate_source_url
from .sources import REMOTE_SOURCES, PLATFORM_LABELS, source_platform
from .models import (
    AISettingsInput,
    LAYOUT_MODES,
    SUBTITLE_STYLES,
    ClipCopyInput,
    ClipEditInput,
    ClipOptions,
    LiveClipInput,
    LiveSessionInput,
    PublishClipInput,
    PublishingSettingsInput,
    SubtitlesInput,
    TikTokGrabInput,
    TikTokRetryInput,
)
from .subtitles import cues_to_srt, rebuild_edited_cues
from .tiktok import (
    TikTokGrabError,
    list_grabs,
    load_grab,
    reset_stale_grabs,
    retry_grab,
    start_grab,
    _grab_out,
)
from .utils import MediaError, binary_status, run_ffmpeg

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("Clipwise")

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}
MUSIC_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}

_health_cache: dict[str, Any] | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    ai.load_settings()
    stale_grabs = reset_stale_grabs()
    if stale_grabs:
        logger.warning(
            "Se marcaron %d descargas de TikTok interrumpidas como fallidas.",
            stale_grabs,
        )
    jobs.start_worker()
    live.recover_stale_sessions()
    yield
    live.stop_all()


app = FastAPI(title="Clipwise AI", version="1.3.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def creator_context(request: Request, call_next):
    creator = request.headers.get("x-Clipwise-creator","local") if os.environ.get("CLIPFORGE_TEAM_ENGINE")=="1" else "local"
    token = studio.creator_id.set(creator)
    try:
        return await call_next(request)
    finally:
        studio.creator_id.reset(token)


@app.exception_handler(publishing.PublishingError)
async def _publishing_error_handler(
    _: Request, exc: publishing.PublishingError
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": str(exc), "code": exc.code},
    )


def _health() -> dict[str, Any]:
    global _health_cache
    if _health_cache is None:
        binaries = binary_status(fast=os.getenv("CLIPFORGE_FAST_HEALTH") == "1")
        _health_cache = {
            "status": "ok",
            "version": "1.3.0",
            "ffmpeg": binaries.get("ffmpeg", {}),
            "ffprobe": binaries.get("ffprobe", {}),
            "whisper_model": settings.whisper_model,
            "llm": "enabled" if settings.llm_enabled else "heuristic",
            "subtitle_styles": list(SUBTITLE_STYLES),
            "default_style": settings.default_subtitle_style,
            "max_clips": settings.default_max_clips,
            "max_upload_mb": settings.max_upload_bytes // (1024 * 1024),
            "max_source_minutes": settings.max_source_seconds // 60,
            "long_source_minutes": settings.long_source_seconds // 60,
            "layout_modes": list(LAYOUT_MODES),
            "context_overlay": True,
        }
    return _health_cache


def _clip_out(clip: dict[str, Any]) -> dict[str, Any]:
    version = quote(str(clip.get("updated_at") or ""))
    video_url = None
    thumb_url = None
    # Rendered files stay available while a clip is re-rendered, so previews
    # and downloads keep working during subtitle edits.
    if clip.get("video_file"):
        video_url = f"/api/clips/{clip['id']}/video.mp4?v={version}"
    if clip.get("thumb_file"):
        thumb_url = f"/api/clips/{clip['id']}/thumb.jpg?v={version}"
    return {
        "id": clip["id"],
        "idx": clip["idx"],
        "start": clip["start"],
        "end": clip["end"],
        "duration": clip.get("duration"),
        "score": clip.get("score"),
        "score_breakdown": clip.get("score_breakdown") or {},
        "category": clip.get("category") or "",
        "title": clip.get("title"),
        "hook": clip.get("hook"),
        "reason": clip.get("reason"),
        "caption": clip.get("caption"),
        "description": clip.get("description") or "",
        "tags": clip.get("tags") or [],
        "style": clip.get("style"),
        "status": clip.get("status"),
        "error": clip.get("error"),
        "subtitles": clip.get("subtitles") or {"cues": []},
        "overlay": clip.get("overlay") or {},
        "video_url": video_url,
        "thumb_url": thumb_url,
        "updated_at": clip.get("updated_at"),
    }


def _clip_text(clip: dict[str, Any]) -> str:
    cues = (clip.get("subtitles") or {}).get("cues") or []
    return " ".join(str(cue.get("text") or "") for cue in cues).strip()


def _publication_for_clip(clip: dict[str, Any], job: dict[str, Any]):
    return build_publication(
        title=str(clip.get("title") or ""),
        hook=str(clip.get("hook") or ""),
        reason=str(clip.get("reason") or ""),
        text=_clip_text(clip),
        category=str(clip.get("category") or ""),
        tags=clip.get("tags") or [],
        meta=job.get("meta") or {},
        language=job.get("language"),
    )


def _regenerate_clip_description(
    clip: dict[str, Any], job: dict[str, Any]
) -> dict[str, Any]:
    publication = _publication_for_clip(clip, job)
    db.update_clip(
        clip["id"],
        description=publication.description,
        caption=publication.caption,
    )
    clip["description"] = publication.description
    clip["caption"] = publication.caption
    return clip


def _ensure_clip_description(
    clip: dict[str, Any], job: dict[str, Any]
) -> dict[str, Any]:
    if str(clip.get("description") or "").strip():
        return clip
    return _regenerate_clip_description(clip, job)


def _job_out(job: dict[str, Any], clips: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    meta = job.get("meta") or {}
    payload = {
        "id": job["id"],
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
        "source_type": job["source_type"],
        "source_url": job.get("source_url"),
        "title": job["title"],
        "status": job["status"],
        "archived": bool(job.get("archived")),
        "stage": job["stage"],
        "progress": job["progress"],
        "error": job.get("error"),
        "duration": job.get("duration"),
        "language": job.get("language"),
        "clips_target": job.get("clips_target"),
        "options": job.get("options") or {},
        "has_music": bool(job.get("music_file")),
        "meta": meta,
        "streamer": meta.get("streamer") or meta.get("channel") or "",
        "game": meta.get("game") or "",
        "is_gaming": bool(meta.get("is_gaming")),
        "long_mode": bool(meta.get("long_mode")),
    }
    if clips is not None:
        payload["clips"] = [
            _clip_out(_ensure_clip_description(clip, job)) for clip in clips
        ]
    return payload


def _workdir(job_id: str) -> Path:
    return settings.jobs_dir / job_id


def _require_job(job_id: str) -> dict[str, Any]:
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")
    return job


def _require_clip(clip_id: str) -> tuple[dict[str, Any], dict[str, Any], Path]:
    clip = db.get_clip(clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip no encontrado.")
    job = db.get_job(clip["job_id"])
    if not job:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")
    return clip, job, _workdir(job["id"])


def _slug(text: str, fallback: str = "clip") -> str:
    slug = re.sub(r"[^\w\- ]+", "", text or "", flags=re.UNICODE)
    slug = re.sub(r"\s+", "-", slug.strip()).strip("-").lower()
    return slug[:60] or fallback


def _safe_title_from_filename(filename: str | None) -> str:
    stem = Path(filename or "video").stem
    title = re.sub(r"[_\-]+", " ", stem).strip()
    return title[:120] or "Video subido"


async def _save_upload(upload: UploadFile, destination: Path, max_bytes: int) -> None:
    size = 0
    try:
        with destination.open("wb") as output:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"El archivo supera el limite de {max_bytes // (1024 * 1024)} MB.",
                    )
                output.write(chunk)
        if size == 0:
            raise HTTPException(status_code=400, detail="El archivo esta vacio.")
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def _srt_for_clip(clip: dict[str, Any], workdir: Path) -> str:
    rendered = workdir / "clips" / clip["id"] / "subs.srt"
    if rendered.exists():
        try:
            return rendered.read_text(encoding="utf-8")
        except OSError:
            pass
    return cues_to_srt(clip.get("subtitles", {}).get("cues", []))


@app.get("/api/account")
def desktop_account():
    return {"hosted": False}


@app.get("/api/health")
def health() -> dict[str, Any]:
    return _health()


@app.get("/api/options")
def options() -> dict[str, Any]:
    return {
        "subtitle_styles": [
            {
                "id": "shorts",
                "name": "Shorts",
                "description": "Una palabra a la vez, mayusculas y borde grueso.",
            },
            {"id": "bold", "name": "Impacto", "description": "Grande, grueso y con palabra resaltada."},
            {"id": "clean", "name": "Limpio", "description": "Elegante y facil de leer."},
            {"id": "neon", "name": "Neon", "description": "Contraste alto con acento cian."},
            {"id": "minimal", "name": "Minimal", "description": "Discreto, para no tapar la imagen."},
            {
                "id": "impact",
                "name": "Impacto",
                "description": "Impact en mayusculas, palabra activa en amarillo.",
            },
            {
                "id": "pill",
                "name": "Pildora",
                "description": "La palabra que suena va dentro de una pildora blanca.",
            },
            {
                "id": "box",
                "name": "Caja",
                "description": "Texto sobre una caja oscura, siempre legible.",
            },
            {
                "id": "yellow",
                "name": "Amarillo",
                "description": "El amarillo clasico de los virales, con borde negro.",
            },
        ],
        "default_style": settings.default_subtitle_style,
        "min_clips": settings.min_clips,
        "max_clips": settings.default_max_clips,
        "layouts": [
            {
                "id": "auto",
                "name": "Auto",
                "description": "Elige la plantilla segun las camaras y el juego.",
            },
            {
                "id": "vertical",
                "name": "Vertical",
                "description": "Recorte vertical clasico con seguimiento de cara.",
            },
            {
                "id": "cam_juego",
                "name": "Camara + juego",
                "description": "Camara arriba y partida abajo.",
            },
            {
                "id": "dos_cams_juego",
                "name": "2 cams + juego",
                "description": "Dos camaras arriba y la partida debajo.",
            },
            {
                "id": "tres_cams_juego",
                "name": "3 cams + juego",
                "description": "Tres camaras arriba y la partida debajo.",
            },
            {
                "id": "dividido",
                "name": "Dividido",
                "description": "Dos camaras apiladas, como una llamada.",
            },
            {
                "id": "trio",
                "name": "Trio",
                "description": "Tres camaras apiladas.",
            },
            {
                "id": "cuarteto",
                "name": "Cuarteto",
                "description": "Cuatro camaras en cuadricula.",
            },
            {
                "id": "trio_juego",
                "name": "Trio con juego",
                "description": "Partida arriba y tres camaras abajo.",
            },
            {
                "id": "spotlight",
                "name": "Spotlight",
                "description": "Lo importante en grande y la escena completa debajo.",
            },
            {
                "id": "centrado",
                "name": "Centrado",
                "description": "El video entero sobre un fondo difuminado.",
            },
            {
                "id": "horizontal",
                "name": "Horizontal",
                "description": "El video completo con bandas arriba y abajo.",
            },
        ],
        "title_card_styles": [
            {"id": "impact", "name": "Impacto"},
            {"id": "clean", "name": "Limpio"},
            {"id": "box", "name": "Caja"},
        ],
        "title_card_positions": [
            {"id": "top", "name": "Arriba"},
            {"id": "center", "name": "Centro"},
            {"id": "bottom", "name": "Abajo"},
        ],
        "context_overlay": True,
        "long_source_minutes": settings.long_source_seconds // 60,
    }


@app.post("/api/jobs", status_code=201)
async def create_job_endpoint(
    source_type: str = Form(...),
    url: str = Form(""),
    options: str = Form("{}"),
    rights_accepted: str = Form("false"),
    streamer_name: str = Form(""),
    game_name: str = Form(""),
    video: UploadFile | None = File(None),
    music: UploadFile | None = File(None),
) -> dict[str, Any]:
    if source_type not in REMOTE_SOURCES | {"url", "upload"}:
        raise HTTPException(status_code=400, detail="Tipo de origen no valido.")

    parsed = ClipOptions.from_raw(options)
    job_id = uuid.uuid4().hex
    workdir = _workdir(job_id)
    title = "Video importado"
    source_url: str | None = None
    source_filename: str | None = None

    try:
        if source_type != "upload":
            if rights_accepted.strip().lower() not in {"true", "1", "yes", "on"}:
                raise HTTPException(
                    status_code=400,
                    detail="Confirma que tienes derechos o permiso para procesar este video.",
                )
            source_url = validate_source_url(url)
            source_type = source_platform(source_url)
            title = f"Video de {PLATFORM_LABELS[source_type]}"
        else:
            if video is None or not video.filename:
                raise HTTPException(status_code=400, detail="Adjunta un archivo de video.")
            suffix = Path(video.filename).suffix.lower()
            if suffix not in VIDEO_EXTENSIONS:
                raise HTTPException(
                    status_code=400,
                    detail="Formato no admitido. Usa MP4, MOV, MKV, WEBM, M4V o AVI.",
                )
            title = _safe_title_from_filename(video.filename)
            source_filename = f"source{suffix}"

        workdir.mkdir(parents=True, exist_ok=True)
        streamer = re.sub(r"\s+", " ", streamer_name or "").strip()[:40]
        game = re.sub(r"\s+", " ", game_name or "").strip()[:60]
        db.create_job(
            job_id=job_id,
            source_type=source_type,
            source_url=source_url,
            title=title,
            options=parsed.model_dump(),
            clips_target=0,
            meta={
                "creator_id": studio.creator_id.get(),
                "streamer": streamer,
                "channel": streamer,
                "game": game,
                "is_gaming": bool(game),
                "source_title": title if source_type == "upload" else "",
            },
        )

        if source_type == "upload":
            assert video is not None and source_filename is not None
            destination = workdir / source_filename
            await _save_upload(video, destination, settings.max_upload_bytes)
            info = inspect_source(destination)
            db.update_job(
                job_id,
                source_file=source_filename,
                duration=round(info["duration"], 3),
                title=title,
            )

        if music is not None and music.filename:
            suffix = Path(music.filename).suffix.lower()
            if suffix not in MUSIC_EXTENSIONS:
                raise HTTPException(
                    status_code=400,
                    detail="Formato de musica no admitido. Usa MP3, WAV, M4A, AAC, OGG o FLAC.",
                )
            music_path = workdir / f"music{suffix}"
            await _save_upload(music, music_path, 100 * 1024 * 1024)
            db.update_job(job_id, music_file=music_path.name)

        jobs.enqueue_job(job_id)
        job = db.get_job(job_id)
        assert job is not None
        return _job_out(job, [])
    except HTTPException:
        db.delete_job(job_id)
        shutil.rmtree(workdir, ignore_errors=True)
        raise
    except (IngestError, MediaError) as exc:
        db.delete_job(job_id)
        shutil.rmtree(workdir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("No se pudo crear el trabajo.")
        db.delete_job(job_id)
        shutil.rmtree(workdir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"No se pudo crear el trabajo: {exc}") from exc


@app.get("/api/jobs")
def list_jobs(archived: bool = False) -> dict[str, Any]:
    return {"jobs": [_job_out(job) for job in db.list_jobs(limit=30, archived=archived)]}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    job = _require_job(job_id)
    return _job_out(job, db.list_clips(job_id))


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict[str, Any]:
    job = _require_job(job_id)
    if job["status"] in {"queued", "processing"}:
        db.update_job(job_id, status="cancelled", stage="cancelled")
    return _job_out(_require_job(job_id))


@app.post("/api/jobs/{job_id}/retry")
def retry_job(job_id: str) -> dict[str, Any]:
    job = _require_job(job_id)
    if job["status"] not in {"failed", "cancelled"}:
        raise HTTPException(
            status_code=409,
            detail="Solo se pueden reintentar trabajos detenidos.",
        )
    if db.list_clips(job_id):
        raise HTTPException(
            status_code=409,
            detail="Este trabajo ya tiene clips. Reintenta los clips que fallaron.",
        )
    if not job.get("source_url") and not job.get("source_file"):
        raise HTTPException(
            status_code=400,
            detail="El trabajo no tiene un origen reutilizable.",
        )
    db.update_job(job_id, status="queued", stage="queued", progress=0, error=None)
    jobs.enqueue_job(job_id)
    return _job_out(_require_job(job_id), db.list_clips(job_id))


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str) -> dict[str, Any]:
    job = _require_job(job_id)
    if job["status"] in {"queued", "processing"}:
        db.update_job(job_id, status="cancelled", stage="cancelled")
    db.delete_job(job_id)
    shutil.rmtree(_workdir(job_id), ignore_errors=True)
    return {"deleted": True}


@app.get("/api/jobs/{job_id}/download.zip")
def download_zip(job_id: str) -> FileResponse:
    job = _require_job(job_id)
    workdir = _workdir(job_id)
    clips = [
        clip
        for clip in db.list_clips(job_id)
        if clip.get("status") == "ready" and clip.get("video_file")
    ]
    available = [clip for clip in clips if (workdir / clip["video_file"]).exists()]
    if not available:
        raise HTTPException(status_code=404, detail="Todavia no hay clips listos para descargar.")

    archive = workdir / f"clips-{uuid.uuid4().hex[:8]}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        lines: list[str] = []
        for index, clip in enumerate(available, start=1):
            clip = _ensure_clip_description(clip, job)
            name = f"{index:02d}-{_slug(clip.get('title') or '', 'clip')}"
            bundle.write(workdir / clip["video_file"], arcname=f"{name}.mp4")
            srt = _srt_for_clip(clip, workdir)
            if srt.strip():
                bundle.writestr(f"{name}.srt", srt)
            bundle.writestr(f"{name}.txt", _publication_text(clip))
            thumbnail = clip.get("thumb_file")
            if thumbnail and (workdir / thumbnail).is_file():
                bundle.write(workdir / thumbnail, arcname=f"{name}.jpg")
            lines.append(
                f"{index}. {clip.get('title') or 'Clip'}\n"
                f"Puntuacion: {clip.get('score')}\n\n"
                f"Descripcion para YouTube:\n{clip.get('description') or ''}\n\n"
                f"Texto para TikTok:\n{clip.get('caption') or ''}\n"
            )
        bundle.writestr("captions.txt", "\n\n".join(lines))

    filename = f"Clipwise-{_slug(job['title'], 'clips')}.zip"
    return FileResponse(
        archive,
        media_type="application/zip",
        filename=filename,
        background=BackgroundTask(lambda: archive.unlink(missing_ok=True)),
    )


@app.get("/api/clips/{clip_id}")
def get_clip(clip_id: str) -> dict[str, Any]:
    clip, job, _ = _require_clip(clip_id)
    return _clip_out(_ensure_clip_description(clip, job))


@app.post("/api/clips/{clip_id}/description")
def regenerate_clip_description(clip_id: str) -> dict[str, Any]:
    clip, job, _ = _require_clip(clip_id)
    from .editorial import polish_moments
    from .moments import _llm_call
    polish_moments([clip], meta=job.get("meta") or {}, language=job.get("language"),
                   call=_llm_call if settings.llm_enabled else None)
    db.update_clip(clip_id, title=clip["title"], description=clip["description"],
                   caption=clip["caption"], tags_json=clip["tags"])
    return _clip_out(db.get_clip(clip_id) or clip)


@app.put("/api/clips/{clip_id}/copy")
def update_clip_copy(clip_id: str, payload: ClipCopyInput) -> dict[str, Any]:
    clip, _, _ = _require_clip(clip_id)
    db.update_clip(clip_id, **payload.model_dump())
    return _clip_out(db.get_clip(clip_id) or clip)


def _publication_text(clip: dict[str, Any]) -> str:
    return (
        f"TÍTULO\n{clip.get('title') or ''}\n\n"
        f"YOUTUBE\n{clip.get('description') or ''}\n\n"
        f"TIKTOK / REELS\n{clip.get('caption') or ''}\n"
    )


@app.get("/api/clips/{clip_id}/publication.txt")
def download_publication(clip_id: str) -> Response:
    clip, job, _ = _require_clip(clip_id)
    clip = _ensure_clip_description(clip, job)
    filename = f"{_slug(clip.get('title') or '', 'publicacion')}.txt"
    return Response(
        content=_publication_text(clip), media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=publication.txt; filename*=UTF-8''{quote(filename)}"},
    )


def _queue_edit(clip_id: str, **fields: Any) -> None:
    if not db.update_clip(clip_id, editable_only=True, status="queued", error=None, **fields):
        raise HTTPException(status_code=409, detail="Otro render de este clip está en curso.")


@app.put("/api/clips/{clip_id}/edit")
def edit_clip(clip_id: str, payload: ClipEditInput) -> dict[str, Any]:
    clip, _, _ = _require_clip(clip_id)
    if clip.get("status") not in {"ready", "failed"}:
        raise HTTPException(status_code=409, detail="Espera a que termine el render para editar este clip.")
    overlay = dict(clip.get("overlay") or {})
    overlay["render_options"] = payload.model_dump(exclude={"subtitle_style"})
    _queue_edit(clip_id, style=payload.subtitle_style, overlay_json=overlay)
    jobs.enqueue_clip(clip_id)
    return _clip_out(db.get_clip(clip_id) or clip)


@app.get("/api/ai/settings")
def get_ai_settings() -> dict[str, Any]:
    return ai.public_settings()


@app.put("/api/ai/settings")
def update_ai_settings(payload: AISettingsInput) -> dict[str, Any]:
    global _health_cache
    try:
        result = ai.save_settings(payload.model_dump())
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _health_cache = None
    return result


@app.post("/api/ai/test")
def test_ai_connection() -> dict[str, Any]:
    return ai.test_connection()


@app.get("/api/publishing/callback")
def hosted_callback(state: str, code: str = "", error: str = ""):
    return Response(publishing.hosted_callback(state, code, error), media_type="text/plain")


@app.get("/api/publishing/settings")
def get_publishing_settings() -> dict[str, Any]:
    return publishing.public_settings()


@app.put("/api/publishing/settings")
def update_publishing_settings(
    payload: PublishingSettingsInput,
) -> dict[str, Any]:
    publishing.save_publishing_settings(payload.model_dump(exclude_none=True))
    return publishing.public_settings()


@app.get("/api/publishing/connections")
def get_publishing_connections() -> dict[str, Any]:
    return {
        "connections": publishing.connections(),
        "settings": publishing.public_settings(),
    }


@app.post("/api/publishing/oauth/{platform}/start")
def start_publishing_oauth(platform: str) -> dict[str, Any]:
    return publishing.start_oauth(platform)


@app.get("/api/publishing/oauth/{platform}/status")
def get_publishing_oauth_status(platform: str, state: str) -> dict[str, Any]:
    return publishing.oauth_status(platform, state)


@app.post("/api/publishing/oauth/{platform}/disconnect")
def disconnect_publishing_account(platform: str) -> dict[str, Any]:
    return publishing.disconnect(platform)


@app.post("/api/clips/{clip_id}/publish", status_code=202)
def publish_clip_endpoint(
    clip_id: str, payload: PublishClipInput
) -> dict[str, Any]:
    return publishing.publish_clip(clip_id, payload.platform)


@app.get("/api/clips/{clip_id}/publish")
def list_clip_publish_records(clip_id: str) -> dict[str, Any]:
    _require_clip(clip_id)
    return {
        "records": [
            publishing.publish_record_out(record)
            for record in db.list_publish_records(clip_id)
        ],
        "connections": publishing.connections(),
    }


@app.get("/api/publishing/records/{record_id}")
def get_publish_record(record_id: str) -> dict[str, Any]:
    record = db.get_publish_record(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Publicación no encontrada.")
    return publishing.publish_record_out(record)


@app.get("/api/clips/{clip_id}/video.mp4")
def stream_clip_video(clip_id: str) -> FileResponse:
    clip, _, workdir = _require_clip(clip_id)
    if not clip.get("video_file"):
        raise HTTPException(status_code=404, detail="El clip todavia no tiene video.")
    path = workdir / clip["video_file"]
    if not path.exists():
        raise HTTPException(status_code=404, detail="Archivo de video no encontrado.")
    return FileResponse(path, media_type="video/mp4")


@app.get("/api/clips/{clip_id}/source.mp4")
def stream_clip_source(clip_id: str) -> FileResponse:
    """Original footage for the browser editor.

    Long jobs download a clip-sized section instead of the whole broadcast;
    the response header tells the browser which absolute time the file starts at.
    """
    clip, job, workdir = _require_clip(clip_id)
    from .pipeline import _ensure_clip_section, _source_path

    offset = 0.0
    try:
        if (job.get("meta") or {}).get("long_mode"):
            path = _ensure_clip_section(job, clip, workdir)
            offset = float(clip["start"])
        else:
            path = _source_path(job, workdir)
    except MediaError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=404, detail="El video original no está disponible para este clip."
        ) from exc
    return FileResponse(
        path,
        media_type="video/mp4",
        headers={
            "X-Clipwise-Source-Offset": f"{offset:.3f}",
            "Access-Control-Expose-Headers": "X-Clipwise-Source-Offset",
        },
    )


@app.post("/api/clips/{clip_id}/browser-render")
async def save_browser_render(
    clip_id: str,
    file: UploadFile = File(...),
    options: str = Form("{}"),
) -> dict[str, Any]:
    """Persist a clip rendered in the browser (Virocut engine).

    The render replaces the server FFmpeg output; the source and the rest of the
    job stay untouched so the editor can keep iterating.
    """
    clip, _, workdir = _require_clip(clip_id)
    try:
        parsed = json.loads(options or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Opciones del editor inválidas.") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="Opciones del editor inválidas.")

    clip_dir = workdir / "clips" / clip_id
    clip_dir.mkdir(parents=True, exist_ok=True)
    suffix = uuid.uuid4().hex[:12]
    video_path = clip_dir / f"video-{suffix}.mp4"
    total = 0
    try:
        with video_path.open("wb") as handle:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > 512 * 1024 * 1024:
                    raise HTTPException(
                        status_code=413, detail="El render supera el límite de 512 MB."
                    )
                handle.write(chunk)
    except Exception:
        video_path.unlink(missing_ok=True)
        raise
    if total < 1024:
        video_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="El render está vacío.")

    from .render import _extract_thumbnail, cleanup_old_outputs
    from .utils import probe_media

    try:
        info = probe_media(video_path)
    except Exception as exc:
        video_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="El archivo no es un video válido.") from exc

    duration = float(info.get("duration") or (float(clip["end"]) - float(clip["start"])))
    thumb_path = clip_dir / f"thumb-{suffix}.jpg"
    try:
        _extract_thumbnail(video_path, thumb_path, duration)
    except Exception:
        thumb_path.unlink(missing_ok=True)

    overlay = dict(clip.get("overlay") or {})
    render_options = dict(overlay.get("render_options") or {})
    render_options["browser_engine"] = True
    render_options["virocut"] = {
        "template": str(parsed.get("template") or "vertical")[:40],
        "caption_style": str(parsed.get("caption_style") or "default")[:40],
        "hook": str(parsed.get("hook") or "")[:160],
        "hook_style": str(parsed.get("hook_style") or "impact")[:40],
        "watermark": str(parsed.get("watermark") or "")[:80],
        "focus_x": _bounded(parsed.get("focus_x"), 0.5),
        "focus_y": _bounded(parsed.get("focus_y"), 0.42),
        "captions_enabled": bool(parsed.get("captions_enabled", True)),
        "background": str(parsed.get("background") or "blur")[:16],
    }
    overlay["render_options"] = render_options

    fields: dict[str, Any] = {
        "status": "ready",
        "error": None,
        "duration": round(duration, 3),
        "video_file": video_path.relative_to(workdir).as_posix(),
        "overlay_json": overlay,
    }
    keep: set[Path] = {video_path}
    if thumb_path.exists():
        fields["thumb_file"] = thumb_path.relative_to(workdir).as_posix()
        keep.add(thumb_path)
    elif clip.get("thumb_file") and (workdir / clip["thumb_file"]).exists():
        keep.add(workdir / clip["thumb_file"])
    db.update_clip(clip_id, **fields)
    cleanup_old_outputs(clip_dir, keep=keep)
    return _clip_out(db.get_clip(clip_id) or clip)


def _bounded(value: Any, default: float) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


@app.get("/api/clips/{clip_id}/thumb.jpg")
def clip_thumbnail(clip_id: str) -> FileResponse:
    clip, _, workdir = _require_clip(clip_id)
    if not clip.get("thumb_file"):
        raise HTTPException(status_code=404, detail="El clip todavia no tiene miniatura.")
    path = workdir / clip["thumb_file"]
    if not path.exists():
        raise HTTPException(status_code=404, detail="Miniatura no encontrada.")
    return FileResponse(path, media_type="image/jpeg")


@app.get("/api/clips/{clip_id}/frame.jpg")
def clip_source_frame(clip_id: str, t: float = 0.0) -> FileResponse:
    """Full source frame for the manual camera editor.

    ``t`` is seconds into the clip, clamped to the clip duration. Frames are
    cached per clip and tenth of a second so dragging the timeline stays cheap.
    """
    clip, job, workdir = _require_clip(clip_id)
    from .pipeline import _source_path

    try:
        source = _source_path(job, workdir)
    except MediaError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    start = float(clip["start"])
    end = float(clip["end"])
    span = max(0.0, end - start)
    stamp = max(0.0, min(max(0.0, span - 0.05), float(t)))
    cache = workdir / "frame_cache"
    cache.mkdir(parents=True, exist_ok=True)
    destination = cache / f"{clip_id}_{int(round(stamp * 10)):06d}.jpg"
    if not destination.exists() or destination.stat().st_size == 0:
        try:
            run_ffmpeg(
                [
                    "-ss",
                    f"{start + stamp:.3f}",
                    "-i",
                    str(source),
                    "-frames:v",
                    "1",
                    "-vf",
                    "scale=960:-2",
                    "-q:v",
                    "3",
                    str(destination),
                ],
                timeout=90,
            )
        except MediaError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
    if not destination.exists() or destination.stat().st_size == 0:
        raise HTTPException(status_code=404, detail="No se pudo extraer el fotograma.")
    return FileResponse(
        destination,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=300"},
    )


@app.get("/api/clips/{clip_id}/subtitles.srt")
def clip_srt(clip_id: str) -> Response:
    clip, _, workdir = _require_clip(clip_id)
    content = _srt_for_clip(clip, workdir)
    if not content.strip():
        raise HTTPException(status_code=404, detail="Este clip no tiene subtitulos.")
    filename = f"{_slug(clip.get('title') or '', 'subtitles')}.srt"
    return Response(
        content=content,
        media_type="application/x-subrip",
        headers={"Content-Disposition": f"attachment; filename=subtitles.srt; filename*=UTF-8''{quote(filename)}"},
    )


@app.put("/api/clips/{clip_id}/subtitles")
def update_subtitles(clip_id: str, payload: SubtitlesInput) -> dict[str, Any]:
    clip, job, _ = _require_clip(clip_id)
    if clip.get("status") not in {"ready", "failed"}:
        raise HTTPException(
            status_code=409,
            detail="Espera a que el clip termine de renderizarse antes de editar los subtitulos.",
        )
    duration = float(clip["end"]) - float(clip["start"])
    rebuilt = rebuild_edited_cues(
        [cue.model_dump() for cue in payload.cues], duration
    )
    if not rebuilt:
        raise HTTPException(status_code=400, detail="Los subtitulos no pueden estar vacios.")
    _queue_edit(clip_id, subtitles_json={"cues": rebuilt})
    updated = db.get_clip(clip_id)
    assert updated is not None
    _regenerate_clip_description(updated, job)
    jobs.enqueue_clip(clip_id)
    return _clip_out(updated)


@app.post("/api/clips/{clip_id}/render")
def rerender_clip(clip_id: str, response: Response) -> dict[str, Any]:
    clip, job, _ = _require_clip(clip_id)
    clip = _ensure_clip_description(clip, job)
    if not db.update_clip(clip_id, editable_only=True, status="queued", error=None):
        response.headers["X-Clipwise-Reused"] = "1"
        return _clip_out(db.get_clip(clip_id) or clip)
    jobs.enqueue_clip(clip_id)
    updated = db.get_clip(clip_id)
    assert updated is not None
    return _clip_out(updated)


@app.get("/api/tiktok/grabs")
def list_tiktok_grabs() -> dict[str, Any]:
    return {"grabs": list_grabs()}


@app.get("/api/tiktok/grabs/{grab_id}")
def get_tiktok_grab(grab_id: str) -> dict[str, Any]:
    grab = load_grab(grab_id)
    if not grab:
        raise HTTPException(status_code=404, detail="Ese grab no existe.")
    return _grab_out(grab)


@app.post("/api/tiktok/grabs", status_code=202)
def create_tiktok_grab(payload: TikTokGrabInput) -> dict[str, Any]:
    url = payload.url.strip()
    if "tiktok.com" not in urlparse(url).netloc:
        raise HTTPException(
            status_code=400,
            detail="Eso no parece una URL de TikTok.",
        )
    return start_grab(url, payload.title, payload.auto_publish)


@app.post("/api/tiktok/grabs/{grab_id}/retry", status_code=202)
def retry_tiktok_grab(grab_id: str, payload: TikTokRetryInput) -> dict[str, Any]:
    try:
        return retry_grab(grab_id, payload.auto_publish)
    except TikTokGrabError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/tiktok/grabs/{grab_id}/video.mp4")
def download_tiktok_grab(grab_id: str) -> Response:
    grab = load_grab(grab_id)
    if not grab or not grab.get("file"):
        raise HTTPException(status_code=404, detail="Ese grab no tiene video.")
    path = Path(grab["file"])
    if not path.is_file():
        raise HTTPException(status_code=404, detail="El archivo ya no esta.")
    safe_name = re.sub(r"[^\w\- ]", "", (grab.get("title") or "tiktok")[:60]).strip()
    return FileResponse(
        path,
        media_type="video/mp4",
        filename=f"{safe_name or 'tiktok'}.mp4",
    )


@app.get("/api/live/sessions")
def list_live_sessions() -> dict[str, Any]:
    return {"sessions": live.list_sessions()}


@app.post("/api/live/sessions", status_code=201)
def create_live_session(payload: LiveSessionInput) -> dict[str, Any]:
    try:
        return live.start_session(payload.url.strip())
    except live.LiveError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/live/sessions/{session_id}/stop")
def stop_live_session(session_id: str) -> dict[str, Any]:
    try:
        return live.stop_session(session_id)
    except live.LiveError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/live/sessions/{session_id}/resume")
def resume_live_session(session_id: str) -> dict[str, Any]:
    try:
        return live.resume_session(session_id)
    except live.LiveError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete("/api/live/sessions/{session_id}", status_code=204)
def delete_live_session(session_id: str) -> Response:
    live.delete_session(session_id)
    return Response(status_code=204)


@app.post("/api/live/sessions/{session_id}/clip")
def clip_live_session(session_id: str, payload: LiveClipInput) -> dict[str, Any]:
    try:
        return live.make_clip(session_id, payload.seconds)
    except live.LiveError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/live/clips/{clip_id}/video.mp4")
def download_live_clip(clip_id: str) -> Response:
    clip = live.load_clip(clip_id)
    if not clip or not clip.get("file"):
        raise HTTPException(status_code=404, detail="Ese clip no existe.")
    path = Path(clip["file"])
    if not path.is_file():
        raise HTTPException(status_code=404, detail="El archivo ya no esta.")
    safe_name = re.sub(r"[^\w\- ]", "", (clip.get("title") or "clip")[:60]).strip()
    return FileResponse(
        path,
        media_type="video/mp4",
        filename=f"{safe_name or 'clip'}.mp4",
    )


app.include_router(studio.router)

if settings.web_dist.exists():
    app.mount("/", StaticFiles(directory=str(settings.web_dist), html=True), name="web")
else:
    @app.get("/")
    def root() -> dict[str, Any]:
        return {
            "name": "Clipwise AI",
            "status": "ok",
            "detail": "El frontend no esta compilado. Ejecuta npm run build en web/.",
            "docs": "/docs",
        }
