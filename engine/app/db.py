from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import closing
from datetime import datetime, timezone
from typing import Any, Iterable
from uuid import uuid4

from .config import settings

_LOCK = threading.RLock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
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
    options_json TEXT NOT NULL DEFAULT '{}',
    meta_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS clips (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    idx INTEGER NOT NULL,
    start REAL NOT NULL,
    end REAL NOT NULL,
    duration REAL,
    score INTEGER NOT NULL DEFAULT 0,
    score_json TEXT,
    category TEXT,
    title TEXT,
    hook TEXT,
    reason TEXT,
    caption TEXT,
    description TEXT,
    tags_json TEXT,
    subtitles_json TEXT,
    overlay_json TEXT NOT NULL DEFAULT '{}',
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

CREATE TABLE IF NOT EXISTS publishing_accounts (
    platform TEXT PRIMARY KEY,
    access_token TEXT NOT NULL,
    refresh_token TEXT,
    expires_at TEXT,
    scope TEXT,
    account_id TEXT,
    account_name TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS publish_records (
    id TEXT PRIMARY KEY,
    clip_id TEXT NOT NULL REFERENCES clips(id) ON DELETE CASCADE,
    platform TEXT NOT NULL,
    status TEXT NOT NULL,
    remote_id TEXT,
    remote_url TEXT,
    error TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS studio_usage (
    job_id TEXT NOT NULL REFERENCES jobs ON DELETE CASCADE,
    model TEXT NOT NULL, calls INTEGER NOT NULL DEFAULT 0, cached INTEGER NOT NULL DEFAULT 0,
    prompt INTEGER NOT NULL DEFAULT 0, completion INTEGER NOT NULL DEFAULT 0,
    metered INTEGER NOT NULL DEFAULT 0, seconds REAL NOT NULL DEFAULT 0,
    PRIMARY KEY(job_id,model)
);
CREATE TABLE IF NOT EXISTS studio_performance (
    clip_id TEXT NOT NULL REFERENCES clips ON DELETE CASCADE, remote_id TEXT NOT NULL,
    views INTEGER NOT NULL, likes INTEGER, comments INTEGER, observed TEXT NOT NULL,
    account_id TEXT NOT NULL, PRIMARY KEY(clip_id,remote_id)
);
CREATE TABLE IF NOT EXISTS studio_presets (
    name TEXT PRIMARY KEY COLLATE NOCASE, settings TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS studio_variants (
    original TEXT NOT NULL REFERENCES clips(id) ON DELETE CASCADE,
    mode TEXT NOT NULL, clip_id TEXT NOT NULL UNIQUE REFERENCES clips(id) ON DELETE CASCADE,
    PRIMARY KEY(original,mode)
);
CREATE TABLE IF NOT EXISTS studio_favorites (
    original TEXT PRIMARY KEY REFERENCES clips(id) ON DELETE CASCADE,
    clip_id TEXT NOT NULL REFERENCES clips(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS studio_creator_choices (
    creator TEXT NOT NULL, original TEXT NOT NULL REFERENCES clips(id) ON DELETE CASCADE,
    clip_id TEXT NOT NULL REFERENCES clips(id) ON DELETE CASCADE, PRIMARY KEY(creator,original)
);
CREATE TABLE IF NOT EXISTS studio_calendar (
    clip_id TEXT PRIMARY KEY REFERENCES clips(id) ON DELETE CASCADE,
    day TEXT NOT NULL, platform TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_publish_clip ON publish_records(clip_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_publish_status ON publish_records(status);
"""

_JOB_FIELDS = {
    "archived",
    "source_type",
    "source_url",
    "source_file",
    "music_file",
    "title",
    "status",
    "stage",
    "progress",
    "error",
    "duration",
    "language",
    "clips_target",
    "options_json",
    "meta_json",
    "updated_at",
}

_CLIP_FIELDS = {
    "start",
    "end",
    "duration",
    "score",
    "score_json",
    "category",
    "title",
    "hook",
    "reason",
    "caption",
    "description",
    "tags_json",
    "subtitles_json",
    "overlay_json",
    "style",
    "status",
    "error",
    "video_file",
    "thumb_file",
    "updated_at",
}

_CLIP_JSON_FIELDS = {"score_json", "tags_json", "subtitles_json", "overlay_json"}

_PUBLISH_FIELDS = {
    "status",
    "remote_id",
    "remote_url",
    "error",
    "metadata_json",
    "updated_at",
}

_PUBLISH_JSON_FIELDS = {"metadata_json"}


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _load(value: Any, default: Any) -> Any:
    if value is None or value == "":
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _job_dict(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    data["options"] = _load(data.pop("options_json", None), {})
    data["meta"] = _load(data.pop("meta_json", None), {})
    return data


def _clip_dict(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    data["score_breakdown"] = _load(data.pop("score_json", None), {})
    data["tags"] = _load(data.pop("tags_json", None), [])
    data["subtitles"] = _load(data.pop("subtitles_json", None), {"cues": []})
    data["overlay"] = _load(data.pop("overlay_json", None), {})
    return data


def _publish_dict(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    data["metadata"] = _load(data.pop("metadata_json", None), {})
    return data


def _ensure_column(
    conn: sqlite3.Connection, table: str, column: str, definition: str
) -> None:
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db() -> None:
    with _LOCK, closing(_connect()) as conn, conn:
        conn.executescript(_SCHEMA)
        conn.execute("INSERT OR IGNORE INTO studio_creator_choices SELECT 'local',original,clip_id FROM studio_favorites")
        conn.execute("DELETE FROM studio_favorites")
        _ensure_column(conn, "jobs", "archived", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "jobs", "meta_json", "TEXT NOT NULL DEFAULT '{}'")
        _ensure_column(conn, "clips", "overlay_json", "TEXT NOT NULL DEFAULT '{}'")
        _ensure_column(conn, "clips", "category", "TEXT")
        _ensure_column(conn, "clips", "description", "TEXT")


def create_job(
    *,
    job_id: str,
    source_type: str,
    source_url: str | None,
    title: str,
    options: dict[str, Any],
    clips_target: int,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = _utc()
    with _LOCK, closing(_connect()) as conn, conn:
        conn.execute(
            """
            INSERT INTO jobs (
                id, created_at, updated_at, source_type, source_url, title,
                status, stage, progress, clips_target, options_json, meta_json
            ) VALUES (?, ?, ?, ?, ?, ?, 'queued', 'queued', 0, ?, ?, ?)
            """,
            (
                job_id,
                now,
                now,
                source_type,
                source_url,
                title,
                clips_target,
                _dump(options),
                _dump(meta or {}),
            ),
        )
    job = get_job(job_id)
    assert job is not None
    return job


def update_job(job_id: str, **fields: Any) -> None:
    values = {key: value for key, value in fields.items() if key in _JOB_FIELDS}
    if not values:
        return
    if "options_json" in values and not isinstance(values["options_json"], str):
        values["options_json"] = _dump(values["options_json"])
    if "meta_json" in values and not isinstance(values["meta_json"], str):
        values["meta_json"] = _dump(values["meta_json"])
    values["updated_at"] = _utc()
    assignments = ", ".join(f"{key} = ?" for key in values)
    with _LOCK, closing(_connect()) as conn, conn:
        conn.execute(
            f"UPDATE jobs SET {assignments} WHERE id = ?",
            (*values.values(), job_id),
        )


def get_job(job_id: str) -> dict[str, Any] | None:
    with _LOCK, closing(_connect()) as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return _job_dict(row) if row else None


def list_jobs(limit: int = 30, archived: bool = False) -> list[dict[str, Any]]:
    with _LOCK, closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE archived = ? ORDER BY created_at DESC LIMIT ?", (int(archived), limit)
        ).fetchall()
    return [_job_dict(row) for row in rows]


def delete_job(job_id: str) -> bool:
    with _LOCK, closing(_connect()) as conn, conn:
        cursor = conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    return cursor.rowcount > 0


def add_clip(
    *,
    clip_id: str,
    job_id: str,
    idx: int,
    start: float,
    end: float,
    duration: float,
    score: int,
    score_breakdown: dict[str, Any],
    title: str,
    hook: str,
    reason: str,
    caption: str,
    tags: list[str],
    subtitles: dict[str, Any],
    style: str,
    status: str = "queued",
    overlay: dict[str, Any] | None = None,
    category: str = "",
    description: str = "",
) -> dict[str, Any]:
    now = _utc()
    with _LOCK, closing(_connect()) as conn, conn:
        conn.execute(
            """
            INSERT INTO clips (
                id, job_id, idx, start, end, duration, score, score_json,
                category, title, hook, reason, caption, description, tags_json,
                subtitles_json, overlay_json, style, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                clip_id,
                job_id,
                idx,
                start,
                end,
                duration,
                score,
                _dump(score_breakdown),
                category,
                title,
                hook,
                reason,
                caption,
                description,
                _dump(tags),
                _dump(subtitles),
                _dump(overlay or {}),
                style,
                status,
                now,
                now,
            ),
        )
    clip = get_clip(clip_id)
    assert clip is not None
    return clip


def update_clip(clip_id: str, *, editable_only: bool = False, **fields: Any) -> bool:
    values = {key: value for key, value in fields.items() if key in _CLIP_FIELDS}
    if not values:
        return False
    for key in _CLIP_JSON_FIELDS:
        if key in values and not isinstance(values[key], str):
            values[key] = _dump(values[key])
    values["updated_at"] = _utc()
    assignments = ", ".join(f"{key} = ?" for key in values)
    status_clause = " AND status IN ('ready', 'failed')" if editable_only else ""
    with _LOCK, closing(_connect()) as conn, conn:
        result = conn.execute(
            f"UPDATE clips SET {assignments} WHERE id = ?{status_clause}",
            (*values.values(), clip_id),
        )
        return result.rowcount > 0


def get_clip(clip_id: str) -> dict[str, Any] | None:
    with _LOCK, closing(_connect()) as conn:
        row = conn.execute("SELECT * FROM clips WHERE id = ?", (clip_id,)).fetchone()
    return _clip_dict(row) if row else None


def list_clips(job_id: str) -> list[dict[str, Any]]:
    with _LOCK, closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT * FROM clips WHERE job_id = ? ORDER BY idx ASC", (job_id,)
        ).fetchall()
    return [_clip_dict(row) for row in rows]


def reset_stale_jobs() -> int:
    now = _utc()
    message = "El servidor se reinicio durante el procesamiento. Vuelve a intentarlo."
    with _LOCK, closing(_connect()) as conn, conn:
        cursor = conn.execute(
            """
            UPDATE jobs
            SET status = 'failed', stage = '', error = ?, updated_at = ?
            WHERE status IN ('queued', 'processing')
            """,
            (message, now),
        )
        conn.execute(
            """
            UPDATE clips
            SET status = 'failed', error = ?, updated_at = ?
            WHERE status IN ('rendering')
            """,
            (message, now),
        )
    return cursor.rowcount


def queued_clip_ids() -> Iterable[str]:
    with _LOCK, closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT id FROM clips WHERE status = 'queued' ORDER BY created_at ASC"
        ).fetchall()
    return [row["id"] for row in rows]


STALE_CLIP_MESSAGE = "El servidor se reinicio durante el procesamiento. Vuelve a intentarlo."


def stale_clip_ids() -> Iterable[str]:
    """Clips whose render was interrupted by a server restart: they were
    marked failed by reset_stale_jobs with the restart message, and deserve
    an automatic re-render instead of a manual retry."""
    with _LOCK, closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT id FROM clips WHERE status = 'failed' AND error = ? ORDER BY created_at ASC",
            (STALE_CLIP_MESSAGE,),
        ).fetchall()
    return [row["id"] for row in rows]


def upsert_publishing_account(
    platform: str,
    *,
    access_token: str,
    refresh_token: str | None,
    expires_at: str | None,
    scope: str | None,
    account_id: str | None,
    account_name: str | None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = _utc()
    with _LOCK, closing(_connect()) as conn, conn:
        conn.execute(
            """
            INSERT INTO publishing_accounts (
                platform, access_token, refresh_token, expires_at, scope,
                account_id, account_name, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(platform) DO UPDATE SET
                access_token = excluded.access_token,
                refresh_token = COALESCE(excluded.refresh_token, publishing_accounts.refresh_token),
                expires_at = excluded.expires_at,
                scope = COALESCE(excluded.scope, publishing_accounts.scope),
                account_id = COALESCE(excluded.account_id, publishing_accounts.account_id),
                account_name = COALESCE(excluded.account_name, publishing_accounts.account_name),
                metadata_json = excluded.metadata_json,
                updated_at = excluded.updated_at
            """,
            (
                platform,
                access_token,
                refresh_token,
                expires_at,
                scope,
                account_id,
                account_name,
                _dump(metadata or {}),
                now,
                now,
            ),
        )
    account = get_publishing_account(platform)
    assert account is not None
    return account


def get_publishing_account(platform: str) -> dict[str, Any] | None:
    with _LOCK, closing(_connect()) as conn:
        row = conn.execute(
            "SELECT * FROM publishing_accounts WHERE platform = ?", (platform,)
        ).fetchone()
    return _publish_dict(row) if row else None


def list_publishing_accounts() -> list[dict[str, Any]]:
    with _LOCK, closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT * FROM publishing_accounts ORDER BY platform ASC"
        ).fetchall()
    return [_publish_dict(row) for row in rows]


def delete_publishing_account(platform: str) -> bool:
    with _LOCK, closing(_connect()) as conn, conn:
        cursor = conn.execute(
            "DELETE FROM publishing_accounts WHERE platform = ?", (platform,)
        )
    return cursor.rowcount > 0


def add_publish_record(
    *,
    clip_id: str,
    platform: str,
    status: str = "queued",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record_id = uuid4().hex
    now = _utc()
    with _LOCK, closing(_connect()) as conn, conn:
        conn.execute(
            """
            INSERT INTO publish_records (
                id, clip_id, platform, status, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (record_id, clip_id, platform, status, _dump(metadata or {}), now, now),
        )
    record = get_publish_record(record_id)
    assert record is not None
    return record


def update_publish_record(record_id: str, **fields: Any) -> None:
    values = {key: value for key, value in fields.items() if key in _PUBLISH_FIELDS}
    if not values:
        return
    for key in _PUBLISH_JSON_FIELDS:
        if key in values and not isinstance(values[key], str):
            values[key] = _dump(values[key])
    values["updated_at"] = _utc()
    assignments = ", ".join(f"{key} = ?" for key in values)
    with _LOCK, closing(_connect()) as conn, conn:
        conn.execute(
            f"UPDATE publish_records SET {assignments} WHERE id = ?",
            (*values.values(), record_id),
        )


def get_publish_record(record_id: str) -> dict[str, Any] | None:
    with _LOCK, closing(_connect()) as conn:
        row = conn.execute(
            "SELECT * FROM publish_records WHERE id = ?", (record_id,)
        ).fetchone()
    return _publish_dict(row) if row else None


def list_publish_records(clip_id: str, limit: int = 20) -> list[dict[str, Any]]:
    with _LOCK, closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT * FROM publish_records WHERE clip_id = ? "
            "ORDER BY created_at DESC LIMIT ?",
            (clip_id, limit),
        ).fetchall()
    return [_publish_dict(row) for row in rows]


def active_publish_record(clip_id: str, platform: str) -> dict[str, Any] | None:
    with _LOCK, closing(_connect()) as conn:
        row = conn.execute(
            "SELECT * FROM publish_records WHERE clip_id = ? AND platform = ? "
            "AND status IN ('queued', 'uploading', 'processing') "
            "ORDER BY created_at DESC LIMIT 1",
            (clip_id, platform),
        ).fetchone()
    return _publish_dict(row) if row else None
