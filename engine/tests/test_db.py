from __future__ import annotations

import sqlite3

from app import db

_OLD_SCHEMA = """
CREATE TABLE jobs (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_url TEXT,
    source_file TEXT,
    music_file TEXT,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    stage TEXT NOT NULL DEFAULT '',
    progress REAL NOT NULL DEFAULT 0,
    error TEXT,
    duration REAL,
    language TEXT,
    clips_target INTEGER NOT NULL DEFAULT 0,
    options_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE clips (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    idx INTEGER NOT NULL,
    start REAL NOT NULL,
    end REAL NOT NULL,
    duration REAL,
    score INTEGER NOT NULL DEFAULT 0,
    score_json TEXT,
    title TEXT,
    hook TEXT,
    reason TEXT,
    caption TEXT,
    tags_json TEXT,
    subtitles_json TEXT,
    style TEXT,
    status TEXT NOT NULL DEFAULT 'queued',
    error TEXT,
    video_file TEXT,
    thumb_file TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_clips_job ON clips(job_id, idx);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at DESC);
"""


def test_init_db_migrates_meta_and_overlay_columns(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(_OLD_SCHEMA)

    monkeypatch.setattr(db.settings, "db_path", db_path)
    db.init_db()

    with sqlite3.connect(db_path) as conn:
        job_columns = {row[1] for row in conn.execute("PRAGMA table_info(jobs)")}
        clip_columns = {row[1] for row in conn.execute("PRAGMA table_info(clips)")}

    assert "meta_json" in job_columns
    assert "overlay_json" in clip_columns
    assert "category" in clip_columns
    assert "description" in clip_columns


def test_jobs_and_clips_round_trip_metadata(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "roundtrip.db"
    monkeypatch.setattr(db.settings, "db_path", db_path)
    db.init_db()

    job = db.create_job(
        job_id="job123456789",
        source_type="youtube",
        source_url="https://youtu.be/abc",
        title="Directo de Roblox",
        options={"layout": "auto", "context_overlay": True},
        clips_target=0,
        meta={
            "streamer": "Dr Donut",
            "game": "Roblox",
            "is_gaming": True,
            "long_mode": True,
        },
    )

    assert job["meta"]["streamer"] == "Dr Donut"
    assert job["meta"]["long_mode"] is True

    clip = db.add_clip(
        clip_id="clip123456789",
        job_id=job["id"],
        idx=0,
        start=10.0,
        end=40.0,
        duration=30.0,
        score=88,
        score_breakdown={"total": 88},
        category="epic",
        title="Nuevo efecto",
        hook="Mira esto",
        reason="Buen gancho",
        caption="#shorts",
        description="El clip muestra el nuevo efecto y la reacción del streamer.",
        tags=["Roblox"],
        subtitles={"cues": []},
        style="shorts",
        overlay={
            "kicker": "DR DONUT · ROBLOX",
            "context": "NUEVO EFECTO DE PULLS",
            "is_gaming": True,
        },
    )

    assert clip["overlay"]["context"] == "NUEVO EFECTO DE PULLS"
    assert clip["category"] == "epic"
    assert clip["description"] == (
        "El clip muestra el nuevo efecto y la reacción del streamer."
    )

    db.update_clip(
        clip["id"],
        overlay_json={
            "kicker": "DR DONUT · ROBLOX",
            "context": "OTRO CONTEXTO",
            "is_gaming": True,
        },
        description="Descripción actualizada.",
    )
    updated = db.get_clip(clip["id"])
    assert updated is not None
    assert updated["overlay"]["context"] == "OTRO CONTEXTO"
    assert updated["description"] == "Descripción actualizada."


def test_update_job_serializes_meta_dict(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "meta.db"
    monkeypatch.setattr(db.settings, "db_path", db_path)
    db.init_db()
    job = db.create_job(
        job_id="job987654321",
        source_type="upload",
        source_url=None,
        title="test facecam",
        options={"layout": "auto"},
        clips_target=0,
        meta={"streamer": "DR DONUT", "game": "Roblox", "is_gaming": True},
    )

    db.update_job(
        job["id"],
        meta_json={"streamer": "DR DONUT", "game": "Roblox", "is_gaming": True},
    )

    updated = db.get_job(job["id"])
    assert updated is not None
    assert updated["meta"]["streamer"] == "DR DONUT"
    assert updated["meta"]["is_gaming"] is True
