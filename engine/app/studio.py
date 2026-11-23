"""Creator workspace. Media and jobs always go through the existing render queue."""

from __future__ import annotations

from contextlib import closing
from contextvars import ContextVar

creator_id = ContextVar("studio_creator", default="local")
from datetime import date, timedelta
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, UploadFile, Response
from pydantic import BaseModel, Field

from . import creative, db
from .models import ClipEditInput

router = APIRouter(prefix="/api/studio")
Platform = Literal["YouTube Shorts", "TikTok", "Instagram Reels", "Facebook Reels"]


def need_clip(clip_id):
    clip = db.get_clip(clip_id)
    if not clip:
        raise HTTPException(404, "Clip inexistente.")
    return clip


def need_job(job_id):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Proyecto inexistente.")
    return job


@router.get("/dna")
def creator_profile():
    return profile_for(creator_id.get())


def profile_for(creator):
    with closing(db._connect()) as conn:
        rows = conn.execute(
            "SELECT c.* FROM studio_creator_choices f JOIN clips c ON c.id=f.clip_id WHERE f.creator=?",
            (creator,),
        ).fetchall()
        observed = conn.execute(
            """SELECT c.category, sum(p.views) views, sum(p.likes) likes
            FROM studio_performance p JOIN clips c ON c.id=p.clip_id JOIN jobs j ON j.id=c.job_id
            WHERE p.likes IS NOT NULL AND coalesce(json_extract(j.meta_json, '$.creator_id'),'local')=?
            GROUP BY c.category HAVING sum(p.views)>=100""",
            (creator,),
        ).fetchall()
    profile = creative.preference_profile([db._clip_dict(row) for row in rows])
    profile["engagement"] = {
        r["category"]: round(r["likes"] / max(1, r["views"]), 4)
        for r in observed
        if r["category"]
    }
    return profile


@router.delete("/dna")
def forget_preferences():
    with closing(db._connect()) as conn, conn:
        conn.execute(
            "DELETE FROM studio_creator_choices WHERE creator=?", (creator_id.get(),)
        )
        conn.execute(
            """DELETE FROM studio_performance WHERE clip_id IN (
            SELECT c.id FROM clips c JOIN jobs j ON j.id=c.job_id
            WHERE coalesce(json_extract(j.meta_json,'$.creator_id'),'local')=?)""",
            (creator_id.get(),),
        )
    return creator_profile()


@router.post("/logo")
async def upload_logo(file: UploadFile):
    import io
    import hashlib
    from PIL import Image, UnidentifiedImageError
    from .config import settings

    raw = await file.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise HTTPException(413, "El logo debe pesar menos de 2 MB.")
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if image.format != "PNG" or image.width * image.height > 4_000_000:
                raise ValueError()
            image.thumbnail((640, 640))
            logo = image.convert("RGBA")
    except (OSError, ValueError, Image.DecompressionBombError, UnidentifiedImageError):
        raise HTTPException(422, "Usa un logo PNG de hasta cuatro megapíxeles.")
    logo_id = hashlib.sha256(raw).hexdigest()[:32]
    folder = settings.data_dir / "brand"
    folder.mkdir(exist_ok=True)
    temporary = folder / (uuid4().hex + ".tmp")
    try:
        logo.save(temporary, "PNG")
        temporary.replace(folder / (logo_id + ".png"))
    finally:
        temporary.unlink(missing_ok=True)
    return {"logo_id": logo_id}


class Preset(BaseModel):
    name: str = Field(min_length=1, max_length=64, pattern=r".*\S.*")
    settings: ClipEditInput


@router.put("/presets")
def save_preset(payload: Preset):
    values = payload.settings.model_dump(exclude={"manual_cams", "title_card"})
    with closing(db._connect()) as conn, conn:
        conn.execute(
            "INSERT INTO studio_presets VALUES (?,?) ON CONFLICT(name) DO UPDATE SET settings=excluded.settings",
            (payload.name.strip(), db._dump(values)),
        )
    return presets()


@router.get("/presets")
def presets():
    with closing(db._connect()) as conn:
        return [
            {"name": row["name"], "settings": db._load(row["settings"], {})}
            for row in conn.execute("SELECT * FROM studio_presets ORDER BY name")
        ]


@router.get("/clips/{clip_id}/editorial")
def editorial(clip_id: str, offset: int = Query(0, ge=0, le=100000)):
    clip = need_clip(clip_id)
    project = need_job(clip["job_id"])
    profile = (
        creator_profile() if project["options"].get("use_creator_profile") else None
    )
    return {
        **creative.assessment(clip),
        "hooks": creative.hook_options(clip, offset, profile),
    }


@router.post("/clips/{clip_id}/hooks")
def generate_hooks(clip_id: str, offset: int = Query(0, ge=0, le=100000)):
    from . import ai, meter
    from .config import settings

    clip = need_clip(clip_id)
    result = editorial(clip_id, offset)
    passage = creative.transcript(clip)
    if not settings.llm_enabled or not passage:
        return result
    with meter.measuring(clip["job_id"]):
        data = ai.complete_json(
            [
                {
                    "role": "system",
                    "content": "Selecciona hasta cinco citas textuales completas de la transcripción para abrir este clip. Prioriza las candidatas sugeridas cuando encajen. Usa solo citas literales intactas de hasta 120 caracteres. Devuelve JSON con hooks, una lista de objetos con text y kind (Pregunta, Curiosidad, Contexto, Directo o Reacción).",
                },
                {
                    "role": "user",
                    "content": db._dump(
                        {
                            "transcript": passage[:9000],
                            "variation": offset,
                            "candidate_quotes_in_preferred_order": [
                                h["text"]
                                for h in result["hooks"]
                                if h["kind"] != "Título editorial"
                            ],
                        }
                    ),
                },
            ]
        )
    sentences = set(creative.evidence_sentences(passage))
    proposals = (data or {}).get("hooks", [])
    if isinstance(proposals, list):
        known = set()
        hooks = []
        for item in proposals[:10]:
            if not isinstance(item, dict):
                continue
            line = item.get("text")
            kind = item.get("kind")
            if (
                isinstance(line, str)
                and line in sentences
                and line not in known
                and len(line) <= 120
            ):
                hooks.append(
                    {
                        "kind": (
                            kind
                            if kind
                            in (
                                "Pregunta",
                                "Curiosidad",
                                "Contexto",
                                "Directo",
                                "Reacción",
                            )
                            else "Cita del clip"
                        ),
                        "text": line,
                    }
                )
                known.add(line)
        result["hooks"] = (
            hooks + [h for h in result["hooks"] if h["text"] not in known]
        )[:6]
    return result


@router.post("/jobs/{job_id}/youtube-stats")
def youtube_stats(job_id: str):
    import requests
    from . import publishing

    need_job(job_id)
    account = db.get_publishing_account("youtube")
    if not account:
        raise HTTPException(
            409, "Conecta tu cuenta de YouTube para leer sus estadísticas."
        )
    with closing(db._connect()) as conn:
        videos = conn.execute(
            """SELECT DISTINCT p.remote_id,p.clip_id FROM publish_records p JOIN clips c ON c.id=p.clip_id
              WHERE c.job_id=? AND p.platform='youtube' AND p.status='published' AND p.remote_id IS NOT NULL""",
            (job_id,),
        ).fetchall()
    if not videos:
        return {"videos": []}
    token = publishing._access_token("youtube")
    measured = []
    for i in range(0, len(videos), 50):
        batch = {r["remote_id"]: r["clip_id"] for r in videos[i : i + 50]}
        try:
            response = requests.get(
                "https://www.googleapis.com/youtube/v3/videos",
                params={"part": "snippet,statistics", "id": ",".join(batch)},
                headers={"Authorization": "Bearer " + token},
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError):
            raise HTTPException(502, "YouTube no devolvió las estadísticas.")
        for item in data.get("items", []):
            remote = item["id"]
            if (
                remote not in batch
                or item.get("snippet", {}).get("channelId") != account["account_id"]
            ):
                continue
            stats = item.get("statistics", {})
            if "viewCount" not in stats:
                continue
            views = int(stats["viewCount"])
            likes = int(stats["likeCount"]) if "likeCount" in stats else None
            comments = int(stats["commentCount"]) if "commentCount" in stats else None
            with closing(db._connect()) as conn, conn:
                conn.execute(
                    "INSERT OR REPLACE INTO studio_performance VALUES (?,?,?,?,?,?,?)",
                    (
                        batch[remote],
                        remote,
                        views,
                        likes,
                        comments,
                        db._utc(),
                        account["account_id"],
                    ),
                )
            measured.append(
                {
                    "clip": batch[remote],
                    "views": views,
                    "likes": likes,
                    "comments": comments,
                }
            )
    return {"videos": measured}


@router.get("/clips/{clip_id}/strategy")
def strategy(clip_id: str):
    import json
    from .config import settings

    clip = need_clip(clip_id)
    subjects = clip.get("tags") or []
    passage = creative.transcript(clip)
    keywords = creative.tokens(passage)
    cutaways = []
    cache = settings.jobs_dir / clip["job_id"] / "transcript-v2.json"
    try:
        segments = json.loads(cache.read_text(encoding="utf-8"))["result"]["segments"]
    except (OSError, KeyError, ValueError, TypeError):
        segments = []
    for s in segments:
        if s["end"] > clip["start"] - 1 and s["start"] < clip["end"] + 1:
            continue
        common = keywords & creative.tokens(s["text"])
        if len(common) >= 2:
            cutaways.append((len(common), s["start"], s["end"], s["text"]))
    unique = []
    for _, start, end, text in sorted(cutaways, key=lambda item: -item[0]):
        if all(abs(start - r["start"]) >= 5 for r in unique):
            unique.append({"start": start, "end": end, "quote": text})
        if len(unique) == 3:
            break
    return {
        "broll": unique,
        "topics": subjects[:4],
        "next_video": (
            f"Desarrolla {subjects[0]} en otro video: retoma la pregunta que abre este clip y muestra un ejemplo."
            if subjects
            else "Revisa las preguntas de este corte para identificar un tema de seguimiento."
        ),
        "basis": creative.assessment(clip),
    }


class Variant(BaseModel):
    mode: Literal["dynamic", "clean", "opening"]


def original_id(conn, clip_id):
    row = conn.execute(
        "SELECT original FROM studio_variants WHERE clip_id=?", (clip_id,)
    ).fetchone()
    return row["original"] if row else clip_id


@router.get("/clips/{clip_id}/battle")
def battle(clip_id: str):
    from .main import _clip_out

    need_clip(clip_id)
    with closing(db._connect()) as conn:
        original = original_id(conn, clip_id)
        rows = conn.execute(
            "SELECT c.*, v.mode FROM studio_variants v JOIN clips c ON c.id=v.clip_id WHERE v.original=? ORDER BY c.idx",
            (original,),
        ).fetchall()
        favorite = conn.execute(
            "SELECT clip_id FROM studio_creator_choices WHERE creator=? AND original=?",
            (creator_id.get(), original),
        ).fetchone()
    return {
        "versions": [
            {"mode": "original", "clip": _clip_out(need_clip(original))},
            *[
                {"mode": row["mode"], "clip": _clip_out(db._clip_dict(row))}
                for row in rows
            ],
        ],
        "favorite": favorite[0] if favorite else None,
    }


@router.post("/clips/{clip_id}/battle")
def create_variant(clip_id: str, payload: Variant, response: Response):
    from .jobs import enqueue_clip

    with closing(db._connect()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        origin = original_id(conn, clip_id)
        row = conn.execute("SELECT * FROM clips WHERE id=?", (origin,)).fetchone()
        if not row:
            raise HTTPException(404, "Clip inexistente.")
        if conn.execute(
            "SELECT 1 FROM studio_variants WHERE original=? AND mode=?",
            (origin, payload.mode),
        ).fetchone():
            response.headers["X-Clipwise-Reused"] = "1"
            return battle(origin)
        if row["status"] != "ready":
            raise HTTPException(409, "El clip original debe estar listo.")
        clip = db._clip_dict(row)
        overlay = clip["overlay"].copy()
        opts = dict(overlay.get("render_options") or {})
        style = clip["style"]
        if payload.mode == "opening":
            hooks = creative.hook_options(clip)
            if not hooks:
                raise HTTPException(
                    409, "Elige un clip con un título o una transcripción."
                )
            opts.update(title_card=hooks[0]["text"], title_card_seconds=3)
        else:
            dynamic = payload.mode == "dynamic"
            style = "impact" if dynamic else "minimal"
            opts.update(dynamic_zoom=dynamic, remove_silences=dynamic)
        overlay["render_options"] = opts
        new_id = uuid4().hex
        new_idx = conn.execute(
            "SELECT MAX(idx)+1 FROM clips WHERE job_id=?", (row["job_id"],)
        ).fetchone()[0]
        data = dict(row)
        data.update(
            id=new_id,
            idx=new_idx,
            style=style,
            overlay_json=db._dump(overlay),
            status="queued",
            error=None,
            video_file=None,
            thumb_file=None,
            created_at=db._utc(),
            updated_at=db._utc(),
        )
        conn.execute(
            f"INSERT INTO clips ({','.join(data)}) VALUES ({','.join('?' for _ in data)})",
            tuple(data.values()),
        )
        conn.execute(
            "INSERT INTO studio_variants VALUES (?,?,?)", (origin, payload.mode, new_id)
        )
    enqueue_clip(new_id)
    return battle(origin)


@router.put("/clips/{clip_id}/favorite")
def favorite(clip_id: str):
    clip = need_clip(clip_id)
    if clip["status"] != "ready":
        raise HTTPException(409, "Espera a que termine el render.")
    with closing(db._connect()) as conn, conn:
        origin = original_id(conn, clip_id)
        conn.execute(
            "INSERT INTO studio_creator_choices VALUES (?,?,?) ON CONFLICT(creator,original) DO UPDATE SET clip_id=excluded.clip_id",
            (creator_id.get(), origin, clip_id),
        )
    return battle(clip_id)


class CalendarItem(BaseModel):
    clip_id: str = Field(min_length=1, max_length=100)
    day: date
    platform: Platform


class Week(BaseModel):
    items: list[CalendarItem] = Field(min_length=1, max_length=7)


@router.get("/calendar")
def calendar():
    with closing(db._connect()) as conn:
        return [
            dict(row)
            for row in conn.execute(
                "SELECT e.*, c.title, c.job_id FROM studio_calendar e JOIN clips c ON c.id=e.clip_id ORDER BY e.day,c.idx"
            )
        ]


@router.delete("/calendar/{clip_id}")
def unschedule(clip_id: str):
    with closing(db._connect()) as conn, conn:
        conn.execute("DELETE FROM studio_calendar WHERE clip_id=?", (clip_id,))
    return {"removed": clip_id}


@router.get("/jobs/{job_id}/week")
def suggest_week(job_id: str, start: date, platform: Platform = "YouTube Shorts"):
    need_job(job_id)
    clips = db.list_clips(job_id)
    with closing(db._connect()) as conn:
        selected = {
            r["original"]: r["clip_id"]
            for r in conn.execute(
                "SELECT * FROM studio_creator_choices WHERE creator=?",
                (creator_id.get(),),
            )
        }
        variants = {
            r["clip_id"] for r in conn.execute("SELECT clip_id FROM studio_variants")
        }
    allowed = {selected.get(c["id"], c["id"]) for c in clips if c["id"] not in variants}
    ranked = creative.week_order(
        [c for c in clips if c["id"] in allowed], creator_profile()
    )
    return [
        {
            "clip_id": c["id"],
            "title": c["title"],
            "description": c["description"],
            "tags": c["tags"],
            "day": start + timedelta(days=i),
            "platform": platform,
            "score": c["score"],
            **creative.assessment(c),
        }
        for i, c in enumerate(ranked)
    ]


@router.put("/jobs/{job_id}/week")
def approve_week(job_id: str, payload: Week):
    need_job(job_id)
    if len({i.clip_id for i in payload.items}) != len(payload.items):
        raise HTTPException(422, "El borrador contiene clips repetidos.")
    with closing(db._connect()) as conn, conn:
        for item in payload.items:
            valid = conn.execute(
                "SELECT 1 FROM clips WHERE id=? AND job_id=? AND status='ready'",
                (item.clip_id, job_id),
            ).fetchone()
            if not valid:
                raise HTTPException(
                    409, "El calendario contiene un clip que ya no está disponible."
                )
            conn.execute(
                "INSERT INTO studio_calendar VALUES (?,?,?) ON CONFLICT(clip_id) DO UPDATE SET day=excluded.day,platform=excluded.platform",
                (item.clip_id, item.day.isoformat(), item.platform),
            )
    return calendar()


@router.post("/jobs/{job_id}/duplicate", status_code=201)
def duplicate(job_id: str):
    from .main import _job_out
    from .project_copy import copy_project

    return _job_out(need_job(copy_project(job_id, creator_id.get())))


@router.get("/jobs/{job_id}/usage")
def project_usage(job_id: str):
    from .config import settings
    import os

    job = need_job(job_id)
    root = settings.jobs_dir / job_id
    total = 0
    for folder, dirs, files in os.walk(root):
        for name in files:
            try:
                total += (Path(folder) / name).stat().st_size
            except FileNotFoundError:
                pass
    clips = db.list_clips(job_id)
    with closing(db._connect()) as conn:
        usage = [
            dict(r)
            for r in conn.execute(
                "SELECT model,calls,cached,prompt,completion,metered,seconds FROM studio_usage WHERE job_id=?",
                (job_id,),
            )
        ]
    import json

    def rate(name):
        value = os.getenv(name)
        try:
            return max(0, float(value)) if value is not None else None
        except ValueError:
            return None

    try:
        rates = json.loads(os.getenv("CLIPFORGE_MODEL_RATES", "{}"))
    except ValueError:
        rates = {}
    api_cost = 0.0
    for row in usage:
        if not row["calls"]:
            continue
        pair = rates.get(row["model"]) if isinstance(rates, dict) else None
        if (
            row["metered"] != row["calls"]
            or not isinstance(pair, list)
            or len(pair) != 2
            or not all(isinstance(n, (int, float)) and n >= 0 for n in pair)
        ):
            api_cost = None
            break
        api_cost += (row["prompt"] * pair[0] + row["completion"] * pair[1]) / 1_000_000
    render_seconds = sum(row["seconds"] for row in usage)
    render_rate = rate("CLIPFORGE_RENDER_USD_HOUR")
    storage_rate = rate("CLIPFORGE_STORAGE_USD_GB_MONTH")
    return {
        "meter": usage,
        "api_usd_estimate": api_cost if usage else None,
        "render_usd_estimate": (
            render_seconds * render_rate / 3600
            if render_rate is not None and render_seconds
            else None
        ),
        "storage_usd_month_estimate": (
            total * storage_rate / 1e9 if storage_rate is not None else None
        ),
        "storage_bytes": total,
        "ready": sum(c["status"] == "ready" for c in clips),
        "media_seconds": round(
            sum(c["duration"] or 0 for c in clips if c["status"] == "ready"), 1
        ),
        "processing_seconds": job["meta"].get("processing_seconds"),
        "analysis_modes": job["meta"].get("analysis_modes", []),
    }


class ProjectEdit(BaseModel):
    title: str | None = Field(
        default=None, min_length=1, max_length=150, pattern=r".*\S.*"
    )
    archived: bool | None = None


@router.patch("/jobs/{job_id}")
def edit_project(job_id: str, payload: ProjectEdit):
    from .main import _job_out

    current = need_job(job_id)
    if payload.archived and current["status"] in {"queued", "processing"}:
        raise HTTPException(409, "Espera a que termine el proyecto para archivarlo.")
    fields = payload.model_dump(exclude_none=True)
    if "title" in fields:
        fields["title"] = fields["title"].strip()
    db.update_job(job_id, **fields)
    return _job_out(need_job(job_id))
