import io
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from app import db, jobs, main, studio, creative, transcribe
from app.config import settings


@pytest.fixture
def api(monkeypatch, tmp_path):
    for name, value in {
        "data_dir": tmp_path,
        "db_path": tmp_path / "studio.sqlite",
        "jobs_dir": tmp_path / "jobs",
        "tmp_dir": tmp_path / "tmp",
    }.items():
        monkeypatch.setattr(settings, name, value)
    settings.ensure_dirs()
    db.init_db()
    db.init_db()
    db.create_job(
        job_id="abc",
        source_type="upload",
        source_url=None,
        title="Partido",
        options={},
        clips_target=1,
    )
    db.update_job("abc", status="ready")
    db.add_clip(
        clip_id="uno",
        job_id="abc",
        idx=0,
        start=0,
        end=15,
        duration=15,
        score=83,
        score_breakdown={"clarity": 78, "retention": 60},
        category="funny",
        title="La primera jugada",
        hook="",
        reason="",
        caption="",
        tags=["pelota"],
        style="clean",
        subtitles={
            "cues": [
                {
                    "text": "¿Por qué esperaste la pelota? Porque el lanzamiento venía lento."
                }
            ]
        },
        status="ready",
    )
    db.update_clip("uno", video_file="one.mp4")
    monkeypatch.setattr(jobs, "enqueue_clip", lambda _: None)
    return TestClient(main.app)


def test_render_variants_are_idempotent_and_preserve_source(api):
    url = "/api/studio/clips/uno/battle"
    with ThreadPoolExecutor(2) as pool:
        responses = list(
            pool.map(lambda _: api.post(url, json={"mode": "clean"}), range(2))
        )
    assert all(r.is_success for r in responses)
    assert any(r.headers.get("x-Clipwise-reused") == "1" for r in responses)
    versions = api.get(url).json()["versions"]
    assert len(versions) == 2 and versions[0]["clip"]["video_url"]
    assert (
        versions[1]["clip"]["id"] != "uno" and versions[1]["clip"]["video_url"] is None
    )


def test_week_approval_is_atomic_and_favorites_learn(api):
    assert api.put("/api/studio/clips/uno/favorite").is_success
    assert api.get("/api/studio/dna").json()["style"] == "clean"
    week = api.get("/api/studio/jobs/abc/week?start=2026-11-21").json()
    assert len(week) == 1 and week[0]["day"] == "2026-11-21"
    assert (
        api.put(
            "/api/studio/jobs/abc/week",
            json={"items": [*week, {**week[0], "clip_id": "missing"}]},
        ).status_code
        == 409
    )
    assert api.get("/api/studio/calendar").json() == []
    assert api.put("/api/studio/jobs/abc/week", json={"items": week}).is_success
    assert api.delete("/api/studio/dna").json()["examples"] == 0
    assert len(api.get("/api/studio/calendar").json()) == 1


def test_brand_and_preset(api):
    png = io.BytesIO()
    Image.new("RGBA", (8, 8), (228, 29, 15, 200)).save(png, "PNG")
    uploaded = api.post(
        "/api/studio/logo", files={"file": ("mark.png", png.getvalue(), "image/png")}
    )
    assert uploaded.is_success
    logo = uploaded.json()["logo_id"]
    assert (settings.data_dir / "brand" / (logo + ".png")).exists()
    assert (
        api.post(
            "/api/studio/logo", files={"file": ("bad.png", b"no image", "image/png")}
        ).status_code
        == 422
    )
    assert api.put(
        "/api/studio/presets",
        json={
            "name": "Liga",
            "settings": {"logo_id": logo, "aspect": "1:1", "caption_color": "#e5f550"},
        },
    ).is_success
    assert api.get("/api/studio/presets").json()[0]["settings"]["logo_id"] == logo
    assert (
        api.put(
            "/api/studio/presets", json={"name": "Liga", "settings": {"aspect": "4:3"}}
        ).status_code
        == 422
    )


def test_hook_draws_from_clip_without_model(api):
    result = api.get("/api/studio/clips/uno/editorial").json()
    assert result["hooks"][0]["text"] in creative.transcript(db.get_clip("uno"))
    assert "cierre" in result["tip"].lower() or "respuesta" in result["tip"].lower()
    assert api.patch(
        "/api/studio/jobs/abc", json={"archived": True, "title": "Final"}
    ).is_success
    assert api.get("/api/jobs").json()["jobs"] == []
    assert api.get("/api/jobs?archived=true").json()["jobs"][0]["title"] == "Final"


def test_complete_asr_cache_uses_source_model_and_language(api, monkeypatch, tmp_path):
    from types import SimpleNamespace

    source = tmp_path / "test.flac"
    source.write_bytes(b"test")
    calls = []
    monkeypatch.setattr(transcribe, "_get_model", lambda: object())

    def decode(*a, **kw):
        calls.append(kw["language"])
        return [], SimpleNamespace(language="es", language_probability=0.94)

    monkeypatch.setattr(transcribe, "_transcribe_single", decode)
    for lang in ("es", "es", "en"):
        transcribe.transcribe(source, 8, language=lang, checkpoint_dir=tmp_path)
    source.write_bytes(b"other")
    transcribe.transcribe(source, 8, language="en", checkpoint_dir=tmp_path)
    assert calls == ["es", "en", "en"]


def test_duplicate_retains_edits_and_independent_files(api):
    original = settings.jobs_dir / "abc"
    original.mkdir()
    (original / "one.mp4").write_bytes(b"test-export")
    db.update_clip("uno", title="Edición final", overlay_json={"brand_text": "Liga"})
    copied = api.post("/api/studio/jobs/abc/duplicate")
    assert copied.status_code == 201, copied.text
    clone = copied.json()
    assert clone["id"] != "abc"
    clip = db.list_clips(clone["id"])[0]
    assert clip["id"] != "uno" and clip["overlay"]["brand_text"] == "Liga"
    assert clip["title"] == "Edición final"
    path = settings.jobs_dir / clone["id"] / clip["video_file"]
    assert path.read_bytes() == b"test-export"
    db.update_clip(clip["id"], title="Otro título")
    assert db.get_clip("uno")["title"] == "Edición final"
    path.unlink()
    assert (original / "one.mp4").is_file()


def test_channel_metrics_follow_project_creator(api):
    from contextlib import closing

    db.update_job("abc", meta_json={"creator_id": "creator-one"})
    with closing(db._connect()) as conn, conn:
        conn.execute(
            "INSERT INTO studio_performance VALUES (?,?,?,?,?,?,?)",
            ("uno", "test-video", 200, 10, 2, "2026-11-21", "test-channel"),
        )
    assert studio.profile_for("creator-one")["engagement"] == {"funny": 0.05}
    assert studio.profile_for("creator-two")["engagement"] == {}
    identity = studio.creator_id.set("creator-two")
    try:
        studio.forget_preferences()
        assert studio.profile_for("creator-one")["engagement"]
    finally:
        studio.creator_id.reset(identity)
    identity = studio.creator_id.set("creator-one")
    try:
        assert studio.forget_preferences()["engagement"] == {}
    finally:
        studio.creator_id.reset(identity)


def test_one_render_claim_for_concurrent_edits(api):
    changes = {"aspect": "1:1", "subtitle_style": "clean"}
    with ThreadPoolExecutor(2) as workers:
        results = list(
            workers.map(
                lambda _: api.put("/api/clips/uno/edit", json=changes), range(2)
            )
        )
    assert sorted(r.status_code for r in results) == [200, 409]
    reused = api.post("/api/clips/uno/render")
    assert reused.is_success and reused.headers.get("x-Clipwise-reused") == "1"


def test_learned_topics_rank_grounded_hooks():
    passage = "Esta mañana todos salimos temprano. En el estadio presenciamos un jonrón increíble."
    clip = {
        "title": "Esta mañana todos salimos temprano.",
        "subtitles": {"cues": [{"text": passage}]},
    }
    choices = creative.hook_options(clip, profile={"topics": {"jonrón": 3}})
    assert "jonrón" in choices[0]["text"]
