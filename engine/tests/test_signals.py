from __future__ import annotations

from app.signals import (
    CATEGORY_ORDER,
    category_label,
    choose_category,
    event_clusters,
    text_affect,
    text_dimensions,
)


def category_for(text: str) -> str:
    affect = text_affect(text)
    return choose_category(text_dimensions(affect), {}, {})[0]


def test_category_set_is_complete_and_labeled() -> None:
    assert len(CATEGORY_ORDER) == 10
    assert category_label("angry") == "ANGRY MOMENTS"
    assert category_label("funny") == "FUNNY MOMENTS"
    assert category_label("crazy_reactions") == "CRAZY REACTIONS"
    assert category_label("epic") == "EPIC MOMENTS"
    assert category_label("unexpected") == "UNEXPECTED MOMENTS"
    assert category_label("scary") == "SCARY MOMENTS"
    assert category_label("fails") == "FAILS"
    assert category_label("wins") == "WINS"
    assert category_label("drama") == "DRAMA"
    assert category_label("shocking") == "SHOCKING MOMENTS"


def test_short_phrase_matching_uses_word_boundaries() -> None:
    passive = text_affect("El sistema siempre funciona y el silencio sigue")
    explicit = text_affect("gg")

    assert passive["celebration"] == 0.0
    assert explicit["celebration"] > 0.0


def test_text_categories_are_separated_by_context() -> None:
    assert category_for("Jajajaja no puede ser, qué risa, me muero") == "funny"
    assert category_for("Estoy harto, eres un tramposo, qué rabia") == "angry"
    assert category_for("No puede ser, qué susto, me dio miedo") == "scary"
    assert category_for("Gané, victoria, GG, lo conseguimos") == "wins"
    assert category_for("Perdí, qué fail, la arruiné") == "fails"
    assert category_for("Se armó la pelea, discusión y traición en el equipo") == "drama"


def test_celebration_shouting_does_not_turn_into_anger() -> None:
    affect = text_affect("¡Lo logramos! ¡Campeón! ¡GG!")
    dimensions = text_dimensions(affect)
    category, scores = choose_category(dimensions, {}, {})

    assert category == "wins"
    assert scores["wins"] > 35.0
    assert scores["angry"] < 12.0


def test_specific_emotion_wins_when_crazy_reaction_is_a_near_tie() -> None:
    # A laugh can sit just under the generic scream/reaction bucket.  The label
    # should land on FUNNY, not on CRAZY REACTIONS, when the margin is small.
    dimensions = {
        "intensity": 0.9,
        "surprise": 0.8,
        "humor": 0.72,
        "humor_raw": 1.0,
        "conversation": 0.5,
        "importance": 0.5,
        "shock": 0.5,
        "fear": 0.2,
        "anger": 0.2,
        "conflict": 0.2,
        "celebration": 0.2,
        "epic": 0.2,
        "loss": 0.1,
        "exaggeration": 0.5,
        "shouting": 0.8,
        "delivery": 0.5,
        "unique_ratio": 0.5,
        "game": 0.3,
    }
    audio = {"intensity": 80, "scream": 0.9, "laughter": 1.0}
    visual = {"reaction": True, "event_strength": 9, "intensity": 80}

    category, scores = choose_category(dimensions, audio, visual)

    assert scores["crazy_reactions"] - scores["funny"] <= 8.0
    assert category == "funny"


def test_event_clusters_merge_context_and_keep_far_apart_events() -> None:
    events = [
        {"kind": "face_reaction", "start": 10.0, "end": 12.0, "score": 60},
        {"kind": "scream", "start": 13.0, "end": 14.0, "score": 80},
        {"kind": "motion_burst", "start": 40.0, "end": 41.0, "score": 55},
    ]

    clusters = event_clusters(events, gap=2.0)

    assert len(clusters) == 2
    assert [event["kind"] for event in clusters[0]] == ["face_reaction", "scream"]
    assert clusters[1][0]["kind"] == "motion_burst"
