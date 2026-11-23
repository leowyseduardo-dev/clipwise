from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app import main, moments
from app.editorial import clean_copy, grounded, polish_moments, story_penalty, topical_tags
from app.pipeline import _section_clip
from app.render import protect_speech


def sample_clip():
    return {
        "id": "editorial-test", "idx": 0, "start": 10.0, "end": 30.0,
        "duration": 18.0, "score": 77, "status": "ready", "style": "bold",
        "title": "El error estaba en el mensaje", "tags": [],
        "description": "Texto guardado. #Shorts", "caption": "Texto corto. #negocio",
        "subtitles": {"cues": [{"start": 0, "end": 8, "text":
            "El error estaba en el mensaje del negocio. Cambiar el mensaje mejoró el resultado del negocio."}]},
    }


def test_copies_cannot_introduce_numbers_or_unrelated_subjects():
    evidence = "El negocio mejoró su resultado al cambiar el mensaje."
    assert grounded("El mensaje que mejoró el negocio", evidence)
    assert not grounded("El negocio ganó 5000 dólares", evidence)
    assert not grounded("La victoria del campeonato mundial", evidence)
    assert clean_copy("Una frase demasiado larga", 12) == ""


def test_relevant_hashtags_prioritize_identity_and_topics():
    tags = topical_tags("El mensaje del negocio fallaba. Cambiar el mensaje mejoró el negocio.",
                        game="", streamer="Ana", tags=["viral", "fyp", "negocio", "fútbol"])
    assert tags[:2] == ["ana", "negocio"]
    assert "negocio" in tags
    assert not {"viral", "fyp", "futbol"} & set(tags)
    assert len(tags) <= 5


def test_gaming_topics_replace_repeated_filler_hashtags():
    tags = topical_tags("Nuevo juego de terror. Nuevo mensaje. Quien tiene el mensaje. Quien juega este juego de terror.")
    assert set(tags) == {"terror", "videojuegos"}


def test_story_checks_penalize_ads_and_missing_answers():
    assert story_penalty(["Usa mi código de descuento para este producto."]) >= 18
    assert story_penalty(["Y entonces cambió todo.", "¿Pero cuál fue el resultado?"]) > 0
    assert story_penalty(["El error estaba en el mensaje.", "Cambiarlo resolvió el problema."]) == 0


@pytest.mark.parametrize("result", [None, [], {"clips": "oops"}, {"clips": [{"id": 99}]},
    {"clips": [{"id": True, "title": "Dato no válido"}]}])
def test_malformed_provider_keeps_local_publication(result):
    clip = sample_clip()
    polish_moments([clip], meta={}, language="es", call=lambda _: result)
    assert clip["title"] == "El error estaba en el mensaje"
    assert "mensaje" in clip["description"]
    assert "#Shorts" in clip["description"]
    assert "no se lo puede creer" not in clip["caption"]
    assert (clip["start"], clip["end"], clip["score"]) == (10, 30, 77)


def test_editorial_pass_rejects_invented_numbers_and_accepts_grounded_copy():
    clip = sample_clip()
    def fake_call(messages):
        assert "Cambiar el mensaje" in messages[1]["content"]
        return {"clips": [{"id": 0, "title": "El negocio ganó 5000 dólares",
            "description": "Cambiar el mensaje mejoró el resultado del negocio.",
            "caption": "El negocio ganó 5000 dólares.", "tags": ["negocio", "viral"]}]}
    polish_moments([clip], meta={}, language="es", call=fake_call)
    assert "5000" not in str(clip)
    assert clip["description"].startswith("Cambiar el mensaje mejoró")
    assert "viral" not in clip["tags"]


def test_silence_edits_never_remove_quiet_words_or_silent_visuals():
    cues = [{"start": 1, "end": 5, "words": [{"start": 2, "end": 3, "w": "voz"}]}]
    removed = protect_speech([(1, 5)], cues)
    assert removed == [(1, 1.88), (3.18, 5)]
    assert protect_speech([(1, 5)], []) == []
    assert protect_speech([(1, 5)], [{"start": 0, "end": 6, "text": "voz"}]) == []


def test_section_rerender_uses_source_span_after_silence_edit():
    assert _section_clip({"start": 100, "end": 130, "duration": 22})["end"] == 30


def test_scene_snapping_does_not_cut_words():
    start, end = moments._snap_bounds(10, 30, [{"start": 10.2, "end": 29.7}])
    assert (start, end) == (10, 30)


def test_diversity_fallback_keeps_high_scoring_distinct_moments():
    candidates = [{"start": i * 30, "end": i * 30 + 20, "score": 90 - i,
                   "category": "funny", "text": ""} for i in range(7)]
    assert len(moments._select(candidates, 7)) == 7


def test_llm_chunks_overlap_to_keep_setup_and_payoff():
    sentences = [{"text": "texto " * 10, "start": i, "end": i + 1} for i in range(130)]
    chunks = moments._chunks(sentences)
    assert len(chunks) >= 3
    assert [i for i, _ in chunks[0][-4:]] == [i for i, _ in chunks[1][:4]]
    assert set(i for chunk in chunks for i, _ in chunk) == set(range(130))


@pytest.fixture
def copy_api(monkeypatch, tmp_path):
    clip = sample_clip()
    monkeypatch.setattr(main, "_require_clip", lambda _: (clip, {"language": "es", "meta": {}}, tmp_path))
    monkeypatch.setattr(main.db, "get_clip", lambda _: deepcopy(clip))
    def update(_, *, editable_only=False, **fields):
        if editable_only and clip["status"] not in {"ready","failed"}:
            return False
        clip.update(fields)
        if "overlay_json" in fields:
            clip["overlay"] = fields["overlay_json"]
        return True
    monkeypatch.setattr(main.db, "update_clip", update)
    monkeypatch.setattr(main.jobs, "enqueue_clip", lambda _: None)
    return TestClient(main.app), clip


def test_copy_save_download_and_validation(copy_api):
    client, clip = copy_api
    data = {"title": "  Nuevo título  ", "description": "Publicación. #tema", "caption": "Caption. #tema"}
    response = client.put("/api/clips/test/copy", json=data)
    assert response.status_code == 200
    assert response.json()["title"] == "Nuevo título"
    download = client.get("/api/clips/test/publication.txt")
    assert download.status_code == 200
    assert "attachment" in download.headers["content-disposition"]
    assert "Nuevo título" in download.text and "Caption. #tema" in download.text
    assert clip["status"] == "ready"
    assert client.put("/api/clips/test/copy", json={**data, "title": "   "}).status_code == 422


def test_edit_keeps_overlay_and_blocks_concurrent_render(copy_api):
    client, clip = copy_api
    clip["overlay"] = {"context": "Contexto original"}
    response = client.put("/api/clips/test/edit", json={"subtitle_style": "clean", "dynamic_zoom": False})
    assert response.status_code == 200
    assert response.json()["overlay"]["context"] == "Contexto original"
    assert response.json()["overlay"]["render_options"]["dynamic_zoom"] is False
    assert response.json()["status"] == "queued"
    assert client.put("/api/clips/test/edit", json={}).status_code == 409
