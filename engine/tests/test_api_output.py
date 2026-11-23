from __future__ import annotations

from app.main import _clip_out


def test_clip_output_exposes_category_and_advanced_scores() -> None:
    output = _clip_out(
        {
            "id": "clip1",
            "idx": 0,
            "start": 10.0,
            "end": 40.0,
            "duration": 30.0,
            "score": 81,
            "score_breakdown": {
                "intensity": 90,
                "surprise": 80,
                "total": 81,
            },
            "category": "crazy_reactions",
            "title": "La reacción lo dice todo",
            "hook": "No puede ser.",
            "caption": "No puede ser lo que acaba de pasar.",
            "description": "El clip muestra la reacción completa y el momento clave.",
            "tags": ["Reacción"],
            "subtitles": {"cues": []},
            "style": "bold",
            "status": "ready",
            "updated_at": "2026-01-01T00:00:00+00:00",
        }
    )

    assert output["category"] == "crazy_reactions"
    assert output["score_breakdown"]["intensity"] == 90
    assert output["description"] == (
        "El clip muestra la reacción completa y el momento clave."
    )
    assert output["caption"] == "No puede ser lo que acaba de pasar."
    assert output["subtitles"]["cues"] == []
