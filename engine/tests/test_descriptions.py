from __future__ import annotations

from app import main
from app.descriptions import (
    _details_from,
    _hashtags,
    _pick_problem,
    build_publication,
)


def _quote_from(description: str) -> str:
    assert "«" in description and "»" in description
    return description.split("«", 1)[1].split("»", 1)[0]


def test_spanish_publication_has_setup_detail_quote_and_standout() -> None:
    publication = build_publication(
        title="¿Cómo que juga el cron 50 horas en Roblox?",
        hook="Pero ¿cómo que juga el cron 50 horas?",
        text=(
            "Pero ¿cómo que juga el cron 50 horas? "
            "A la Google Chrome 50 horas. "
            "¿Qué haces tú en Google Chrome la semana? "
            "Es imposible, tío. "
            "Al final lo dejo."
        ),
        category="funny",
        meta={
            "streamer": "Adrity 35",
            "game": "Roblox",
            "source_title": "Tiempo de uso de aplicaciones de seguidores",
        },
        language="es",
    )

    description = publication.description
    assert "Adrity 35" in description
    assert "50 horas" in description
    assert "Fragmento de Adrity 35." in description
    assert "#Shorts" in description
    # The YouTube description quotes evidence, never the garbled title.
    assert "juga el cron 50 horas en roblox" not in description.lower()
    assert "50 horas" in publication.caption
    assert publication.caption.count("#") <= 5


def test_english_publication_uses_english_labels_and_hashtags() -> None:
    publication = build_publication(
        title="He spent 36 hours in one game",
        text=(
            "I can't believe he spent 36 hours in one game. "
            "That's impossible. "
            "What is wrong with him?"
        ),
        category="crazy_reactions",
        meta={
            "streamer": "Nova",
            "game": "Roblox",
            "source_title": "Viewer habits",
        },
        language="en",
    )

    assert "Excerpt from Nova." in publication.description
    assert "36 hours" in publication.description
    assert "#Shorts" in publication.description
    assert "#roblox" in publication.caption
    assert "36 hours" in publication.caption


def test_pick_problem_rejects_a_line_that_only_repeats_the_title() -> None:
    title = "¿Qué es esta mierda que no quiero ver esta puta mierda en Roblox?"
    quote = _pick_problem(
        ["¿Qué es esta mierda que no quiero ver esta puta mierda?"],
        title,
        "es",
        "Tiempo de uso de aplicaciones de seguidores Roblox",
    )

    assert quote == ""


def test_word_time_details_are_normalized_and_tiny_ones_are_ignored() -> None:
    details = _details_from("Esto es una mierda, cinco horas y media diarias.")

    assert "5 horas" in details
    assert details.count("5 horas") == 1
    assert "1 minuto" not in _details_from("Espera un minuto.")


def test_hashtags_respect_platform_limits() -> None:
    tags = ["Roblox", "Gaming", "Reaction", "Funny", "Shorts", "Viral", "Extra", "Clip"]
    youtube = _hashtags(
        lang="es",
        category="funny",
        game="Roblox",
        streamer="Adrity 35",
        tags=tags,
        platform="youtube",
    )
    tiktok = _hashtags(
        lang="es",
        category="funny",
        game="Roblox",
        streamer="Adrity 35",
        tags=tags,
        platform="tiktok",
    )

    assert len(youtube.split()) <= 8
    assert len(tiktok.split()) <= 5
    assert youtube.startswith("#Shorts")
    assert tiktok.startswith("#tiktok")


def test_caption_uses_the_problem_when_there_is_no_number() -> None:
    publication = build_publication(
        title="¿Uy que gente más rara me ve en Roblox?",
        text=(
            "Al fondo es imposible hacer nada con niños pequeños. "
            "La gente es tonta, de lo juro."
        ),
        category="crazy_reactions",
        meta={
            "streamer": "Adrity 35",
            "game": "Roblox",
            "source_title": "Tiempo de uso de aplicaciones de seguidores",
        },
        language="es",
    )

    # Evidence quotes land in both surfaces; the caption leads with the
    # opening quote for TikTok.
    assert "imposible hacer nada" in publication.description
    assert "Al fondo es imposible" in publication.caption
    assert "Fragmento de Adrity 35." in publication.description


def test_publication_without_metadata_still_has_context_and_standout() -> None:
    publication = build_publication(
        title="Se quedó sin palabras",
        text="No puede ser, se quedó sin palabras. Fue un momento increíble.",
        category="unexpected",
        language="es",
    )

    assert "se quedó sin palabras" in publication.description
    assert "#Shorts" in publication.description
    assert "None" not in publication.description
    assert publication.caption
    assert "None" not in publication.caption


def test_ensure_clip_description_backfills_and_persists(monkeypatch) -> None:
    updates: dict[str, str] = {}

    def fake_update(clip_id: str, **fields: str) -> None:
        assert clip_id == "clip1"
        updates.update(fields)

    monkeypatch.setattr(main.db, "update_clip", fake_update)
    clip = {
        "id": "clip1",
        "title": "¿Cómo que juga el cron 50 horas en Roblox?",
        "hook": "Pero ¿cómo que juga el cron 50 horas?",
        "reason": "Clip autocontenido que ritmo agil.",
        "category": "funny",
        "tags": ["Roblox"],
        "subtitles": {
            "cues": [
                {
                    "text": (
                        "Pero ¿cómo que juga el cron 50 horas? "
                        "¿Qué haces tú en Google Chrome la semana?"
                    )
                }
            ]
        },
        "description": "",
    }
    job = {
        "language": "es",
        "meta": {
            "streamer": "Adrity 35",
            "game": "Roblox",
            "source_title": "Tiempo de uso de aplicaciones de seguidores",
        },
    }

    result = main._ensure_clip_description(clip, job)

    assert result["description"]
    assert updates["description"] == result["description"]
    assert updates["caption"] == result["caption"]
    assert "50 horas" in result["description"]

    updates.clear()
    existing = {
        **clip,
        "description": "Descripción ya guardada.",
        "caption": "Caption ya guardado.",
    }
    same = main._ensure_clip_description(existing, job)
    assert same["description"] == "Descripción ya guardada."
    assert updates == {}
