from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app import pipeline


def test_section_clip_is_clip_relative() -> None:
    clip = {"id": "abc", "start": 120.0, "end": 150.0, "duration": 30.0}

    local = pipeline._section_clip(clip)

    assert local["start"] == 0.0
    assert local["end"] == 30.0
    assert local["id"] == "abc"


def test_require_free_space_rejects_a_full_disk(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        pipeline.shutil,
        "disk_usage",
        lambda path: SimpleNamespace(free=10 * 1024 * 1024),
    )

    with pytest.raises(pipeline.MediaError, match="espacio libre"):
        pipeline._require_free_space(tmp_path, 100 * 1024 * 1024, "grabar")


def test_ensure_clip_section_reuses_a_valid_section(tmp_path, monkeypatch) -> None:
    clip = {"id": "clip1", "start": 10.0, "end": 40.0}
    workdir = tmp_path / "job"
    section = workdir / "clips" / "clip1" / "section.mp4"
    section.parent.mkdir(parents=True)
    section.write_bytes(b"x" * 4096)
    monkeypatch.setattr(pipeline, "probe_media", lambda path: {"duration": 30.0})
    called = False

    def fake_download(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("no debe descargar una seccion valida")

    monkeypatch.setattr(pipeline, "download_source_section", fake_download)

    result = pipeline._ensure_clip_section(
        {"source_url": "https://www.youtube.com/watch?v=abc"},
        clip,
        workdir,
        info={"duration": 100.0},
        used_auth={},
    )

    assert result == section
    assert called is False


def test_ensure_clip_section_downloads_when_cache_is_invalid(
    tmp_path, monkeypatch
) -> None:
    clip = {"id": "clip2", "start": 10.0, "end": 40.0}
    workdir = tmp_path / "job"
    section = workdir / "clips" / "clip2" / "section.mp4"
    section.parent.mkdir(parents=True)
    section.write_bytes(b"x" * 4096)

    def fake_probe(path: Path):
        if Path(path) == section:
            raise pipeline.MediaError("corrupt")
        return {"duration": 30.0}

    def fake_download(url, job_dir, info, auth, start, end, destination, **kwargs):
        destination.write_bytes(b"y" * 4096)
        return destination

    monkeypatch.setattr(pipeline, "probe_media", fake_probe)
    monkeypatch.setattr(pipeline, "download_source_section", fake_download)

    result = pipeline._ensure_clip_section(
        {"source_url": "https://www.youtube.com/watch?v=abc"},
        clip,
        workdir,
        info={"duration": 100.0},
        used_auth={},
    )

    assert result == section
    assert section.read_bytes() == b"y" * 4096


def test_mark_rerendered_job_ready_closes_a_failed_job(monkeypatch) -> None:
    updates: list[tuple[str, dict]] = []
    monkeypatch.setattr(pipeline.db, "get_job", lambda job_id: {"id": job_id, "status": "failed"})
    monkeypatch.setattr(
        pipeline.db,
        "list_clips",
        lambda job_id: [{"id": "a", "status": "ready"}, {"id": "b", "status": "ready"}],
    )
    monkeypatch.setattr(
        pipeline.db,
        "update_job",
        lambda job_id, **fields: updates.append((job_id, fields)),
    )

    pipeline._mark_rerendered_job_ready("job1")

    assert updates == [
        (
            "job1",
            {"status": "ready", "stage": "done", "progress": 100, "error": None},
        )
    ]


def test_mark_rerendered_job_ready_keeps_job_failed_with_open_clips(monkeypatch) -> None:
    updates: list[tuple[str, dict]] = []
    monkeypatch.setattr(pipeline.db, "get_job", lambda job_id: {"id": job_id, "status": "failed"})
    monkeypatch.setattr(
        pipeline.db,
        "list_clips",
        lambda job_id: [{"id": "a", "status": "ready"}, {"id": "b", "status": "failed"}],
    )
    monkeypatch.setattr(
        pipeline.db,
        "update_job",
        lambda job_id, **fields: updates.append((job_id, fields)),
    )

    pipeline._mark_rerendered_job_ready("job1")

    assert updates == []


def test_mark_rerendered_job_ready_ignores_healthy_jobs(monkeypatch) -> None:
    updates: list[tuple[str, dict]] = []
    monkeypatch.setattr(pipeline.db, "get_job", lambda job_id: {"id": job_id, "status": "ready"})
    monkeypatch.setattr(pipeline.db, "list_clips", lambda job_id: [{"id": "a", "status": "ready"}])
    monkeypatch.setattr(
        pipeline.db,
        "update_job",
        lambda job_id, **fields: updates.append((job_id, fields)),
    )

    pipeline._mark_rerendered_job_ready("job1")

    assert updates == []
