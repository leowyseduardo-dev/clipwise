"""Copy a finished project's editable state and media into an independent project."""

import json
import os
import shutil
from contextlib import closing
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from . import db
from .config import settings


def _copy_file(source, target, immutable=False):
    target.parent.mkdir(parents=True, exist_ok=True)
    if immutable:
        try:
            os.link(source, target)
            return
        except OSError:
            pass
    shutil.copyfile(source, target)


def _insert(conn, table, row):
    keys = ", ".join(row)
    placeholders = ", ".join("?" for _ in row)
    conn.execute(
        f"INSERT INTO {table} ({keys}) VALUES ({placeholders})", tuple(row.values())
    )


def copy_project(job_id, creator):
    new_id = uuid4().hex
    old = settings.jobs_dir / job_id
    folder = settings.jobs_dir / new_id
    with closing(db._connect()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        job = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if job is None:
            raise HTTPException(404, "Proyecto inexistente.")
        clips = conn.execute("SELECT * FROM clips WHERE job_id=?", (job_id,)).fetchall()
        if job["status"] in {"queued", "processing"} or any(
            c["status"] in {"rendering", "queued"} for c in clips
        ):
            raise HTTPException(
                409, "Espera a que termine el procesamiento antes de duplicar."
            )
        ids = {c["id"]: uuid4().hex for c in clips}
        folder.mkdir(parents=True)
        try:
            for field in {
                job["source_file"],
                job["music_file"],
                "working.mp4",
                "transcript-v2.json",
            }:
                if field and Path(field).name == field and (old / field).is_file():
                    _copy_file(
                        old / field,
                        folder / field,
                        immutable=field != "transcript-v2.json",
                    )
            row = dict(job)
            meta = json.loads(row["meta_json"] or "{}")
            meta.pop("processing_seconds", None)
            meta.update(creator_id=creator)
            now = db._utc()
            row.update(
                id=new_id,
                created_at=now,
                updated_at=now,
                archived=0,
                title="Copia · " + row["title"],
                meta_json=db._dump(meta),
            )
            _insert(conn, "jobs", row)
            for clip in clips:
                row = dict(clip)
                new_clip = ids[clip["id"]]
                new_dir = Path("clips") / new_clip
                for key in ("video_file", "thumb_file"):
                    if not row[key]:
                        continue
                    source = (old / row[key]).resolve()
                    if not source.is_relative_to(old.resolve()) or not source.is_file():
                        raise HTTPException(
                            409, "Falta un archivo exportado del proyecto original."
                        )
                    destination = new_dir / source.name
                    _copy_file(source, folder / destination, immutable=True)
                    row[key] = destination.as_posix()
                for name in ("subs.ass", "subs.srt", "section.mp4", "silences.json"):
                    source = old / "clips" / clip["id"] / name
                    if source.is_file():
                        _copy_file(source, folder / new_dir / name)
                row.update(id=new_clip, job_id=new_id, created_at=now, updated_at=now)
                _insert(conn, "clips", row)
            variants = conn.execute(
                "SELECT v.* FROM studio_variants v JOIN clips c ON c.id=v.original WHERE c.job_id=?",
                (job_id,),
            )
            for v in variants:
                conn.execute(
                    "INSERT INTO studio_variants VALUES (?,?,?)",
                    (ids[v["original"]], v["mode"], ids[v["clip_id"]]),
                )
            conn.commit()
        except BaseException:
            shutil.rmtree(folder, ignore_errors=True)
            raise
    return new_id
