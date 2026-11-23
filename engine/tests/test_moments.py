from __future__ import annotations

from types import SimpleNamespace

import pytest

from app import moments as moments_module
from app.moments import (
    _select,
    _trim_to_speech,
    build_sentences,
    desired_clip_count,
    generate_moments,
    words_in_range,
)


def word(text: str, start: float, end: float) -> dict[str, object]:
    return {"w": text, "start": start, "end": end, "p": 1.0}


def test_build_sentences_flushes_on_gap_and_punctuation() -> None:
    segments = [
        {
            "words": [
                word("Hola", 0.0, 0.3),
                word("mundo.", 0.35, 0.7),
                word("Otra", 1.8, 2.1),
            ]
        }
    ]

    sentences = build_sentences(segments)

    assert [sentence["text"] for sentence in sentences] == ["Hola mundo.", "Otra"]
    assert sentences[0]["start"] == 0.0
    assert sentences[0]["end"] == 0.7
    assert sentences[1]["start"] == 1.8


def test_build_sentences_ignores_empty_segments() -> None:
    assert build_sentences([]) == []
    assert build_sentences([{"words": []}]) == []


def test_words_in_range_uses_exclusive_boundaries() -> None:
    segments = [
        {
            "words": [
                word("uno", 0.0, 0.5),
                word("dos", 1.0, 1.5),
                word("tres", 2.0, 2.5),
            ]
        }
    ]

    assert len(words_in_range(segments, 0.4, 2.1)) == 3
    assert words_in_range(segments, 1.5, 2.0) == []


def test_desired_clip_count_rules() -> None:
    assert desired_clip_count(600.0, 3) == 5
    assert desired_clip_count(600.0, 99) == 15
    assert desired_clip_count(20.0, None) == 1
    assert desired_clip_count(60.0, None) == 2
    assert desired_clip_count(120.0, None) == 3
    assert desired_clip_count(299.0, None) == 5
    assert desired_clip_count(300.0, None) == 8
    assert desired_clip_count(600.0, None) == 12
    assert desired_clip_count(1800.0, None) == 15


SENTENCES = [
    "Esto es el secreto que nadie te cuenta sobre el dinero.",
    "La mayoria comete el mismo error cuando empieza un negocio.",
    "Nadie te ensena como funciona el sistema por dentro.",
    "Hay una verdad incomoda detras de cada resultado.",
    "Si entiendes esto, cambias la forma de tomar decisiones.",
    "El problema no es el precio, es la falta de claridad.",
    "Un estudio encontro que el ochenta por ciento falla.",
    "La conclusion es simple: mide antes de escalar.",
    "Cuando empezo, no tenia dinero ni contactos.",
    "Entonces probo una estrategia distinta cada semana.",
    "Al final descubrio que el error estaba en el mensaje.",
    "Ese detalle cambio por completo el resultado.",
    "No necesitas mas herramientas, necesitas criterio.",
    "El truco es reducir el ruido y escuchar la senal.",
    "Cada decision pequena mueve la aguja con el tiempo.",
    "La gente subestima el coste de empezar tarde.",
    "Aqui esta el dato que casi nadie comparte en publico.",
    "Si lo aplicas hoy, manana ya notas la diferencia.",
    "El mejor consejo suena aburrido hasta que funciona.",
    "Evita copiar el plan de alguien que no tiene tu contexto.",
    "La historia se repite cuando no miras los numeros.",
    "Pregunta por que antes de preguntar como hacerlo.",
    "Una buena pregunta vale mas que diez respuestas rapidas.",
    "El resultado llego cuando dejo de perseguir atajos.",
    "Nunca subestimes el poder de una prueba pequena.",
    "Esto es lo que nadie te dice sobre vender un producto.",
    "La confianza se construye con pruebas, no con promesas.",
    "Si el mensaje no conecta, el mejor producto parece malo.",
    "Aprende a leer el contexto antes de lanzar la campana.",
    "Al final, la constancia gana a la intensidad.",
]


def build_segments(
    per_word: float = 0.32, gap: float = 0.35, repeats: int = 3
) -> tuple[list[dict], float]:
    words: list[dict[str, object]] = []
    cursor = 0.0
    for _ in range(repeats):
        for sentence in SENTENCES:
            for token in sentence.split():
                words.append(word(token, round(cursor, 3), round(cursor + per_word, 3)))
                cursor += per_word
            cursor += gap
    chunks: list[dict] = []
    for index in range(0, len(words), 12):
        chunk = words[index : index + 12]
        chunks.append(
            {
                "start": chunk[0]["start"],
                "end": chunk[-1]["end"],
                "text": " ".join(str(item["w"]) for item in chunk),
                "words": chunk,
            }
        )
    return chunks, cursor


def test_generate_moments_returns_self_contained_windows(monkeypatch) -> None:
    monkeypatch.setattr(moments_module, "_llm_candidates", lambda *args, **kwargs: [])
    segments, duration = build_segments()
    options = SimpleNamespace(subtitle_style="bold")

    clips = generate_moments(
        segments,
        [],
        duration=duration,
        options=options,
        requested=5,
        language="es",
    )

    assert len(clips) == 5
    ordered = sorted(clips, key=lambda item: item["start"])
    for clip in ordered:
        assert clip["end"] > clip["start"]
        assert 14.5 <= clip["duration"] <= 90.5
        assert clip["end"] <= duration + 0.01
        assert 1 <= clip["score"] <= 100
        assert set(clip["score_breakdown"]) >= {
            "hook",
            "clarity",
            "interest",
            "pacing",
            "retention",
            "total",
        }
        assert clip["title"]
        assert clip["caption"]
        assert clip["description"]
        assert clip["description"] != clip["title"]
        # YouTube descriptions carry evidence + hashtags; the caption is the
        # TikTok-side copy. Neither includes the legacy "Lo que destaca:" line.
        assert "#Shorts" in clip["description"]
        assert clip["subtitles"]["cues"]
    for current, following in zip(ordered, ordered[1:]):
        assert following["start"] >= current["end"] - 0.01


def test_generate_moments_titles_summarize_final_window(monkeypatch) -> None:
    monkeypatch.setattr(moments_module, "_llm_candidates", lambda *args, **kwargs: [])
    segments, duration = build_segments()
    sentences = build_sentences(segments)

    clips = generate_moments(
        segments,
        [],
        duration=duration,
        options=SimpleNamespace(subtitle_style="bold"),
        requested=5,
        language="es",
    )

    assert len(clips) == 5
    for clip in clips:
        window = [
            item
            for item in sentences
            if item["start"] >= clip["start"] - 0.2
            and item["end"] <= clip["end"] + 0.2
        ]
        assert window
        assert clip["title"] != window[0]["text"]
        assert clip["title"] != "Momento destacado"
        assert clip["context"] == clip["title"]


def test_generate_moments_llm_missing_title_uses_summary(monkeypatch) -> None:
    monkeypatch.setattr(moments_module.settings, "llm_api_key", "test-key")
    monkeypatch.setattr(moments_module, "_heuristic_candidates", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        moments_module,
        "_llm_call",
        lambda messages: {
            "clips": [
                {
                    "start_id": 0,
                    "end_id": 4,
                    "score": 98,
                }
            ]
        },
    )
    segments, duration = build_segments()

    clips = generate_moments(
        segments,
        [],
        duration=duration,
        options=SimpleNamespace(subtitle_style="bold"),
        requested=5,
        language="es",
    )

    assert len(clips) == 1
    assert clips[0]["title"] != "Momento destacado"
    assert clips[0]["title"] != SENTENCES[0]
    assert any(
        keyword in clips[0]["title"].lower()
        for keyword in ("secreto", "dinero", "error", "sistema", "verdad")
    )


def test_generate_moments_falls_back_without_transcript() -> None:
    scenes = [{"start": 0.0, "end": 20.0}, {"start": 22.0, "end": 50.0}]

    clips = generate_moments(
        [],
        scenes,
        duration=60.0,
        options=SimpleNamespace(subtitle_style="clean"),
        requested=None,
        language=None,
    )

    assert len(clips) == 2
    assert [clip["start"] for clip in clips] == [0.0, 22.0]
    assert all(clip["subtitles"]["cues"] == [] for clip in clips)
    assert all(clip["score"] == 38 for clip in clips)


def test_generate_moments_without_scenes_or_speech() -> None:
    clips = generate_moments(
        [],
        [],
        duration=100.0,
        options=SimpleNamespace(subtitle_style="minimal"),
        requested=None,
        language=None,
    )

    assert len(clips) == 2
    assert clips[0]["start"] == 0.0
    assert clips[0]["end"] == 45.0
    assert clips[1]["start"] == 47.0


def test_trim_to_speech_removes_filler_and_dead_air() -> None:
    words = [
        word("bueno", 10.0, 10.2),
        word("esto", 10.25, 10.5),
        word("importa", 10.55, 10.9),
        word("vale", 20.0, 20.2),
    ]

    start, end = _trim_to_speech(9.4, 21.0, words, 30.0)

    assert start == pytest.approx(10.17)
    assert end == pytest.approx(20.55)

def _candidate(index: float, score: float, category: str = "funny") -> dict[str, object]:
    return {
        "start": index * 100.0,
        "end": index * 100.0 + 30.0,
        "duration": 30.0,
        "score": score,
        "category": category,
        "source": "text",
        "sentences": [{"text": "algo paso aqui", "start": index * 100.0, "end": index * 100.0 + 4.0}],
    }


def test_select_never_ships_candidates_below_the_hard_floor() -> None:
    pool = [_candidate(0, 82.0), _candidate(1, 71.0)]
    pool.extend(_candidate(i + 2, 44.0) for i in range(3))

    chosen = _select(pool, target=5)

    # Strong moments exist, so the 44s are noise and never ship — a shorter
    # reel beats a padded one.
    assert [c["score"] for c in chosen] == [82.0, 71.0]


def test_select_prefers_strong_clips_over_filling_the_count() -> None:
    pool = [_candidate(0, 82.0), _candidate(1, 71.0), _candidate(2, 53.0), _candidate(3, 41.0)]

    chosen = _select(pool, target=4)

    # 41 is under the hard floor and never ships; 53 fills the last slot.
    assert [c["score"] for c in chosen] == [82.0, 71.0, 53.0]


def test_select_returns_best_available_when_everything_is_weak() -> None:
    pool = [_candidate(i, 40.0 + i) for i in range(4)]

    chosen = _select(pool, target=2)

    # Empty reel or flat fallback is worse than the best two moments.
    assert [c["score"] for c in chosen] == [43.0, 42.0]

def test_opening_credits_only_evidence_visible_or_audible_in_first_second():
    words = [word("Hola", 10.0, 10.4), word("¡Cuidado!", 11.0, 11.3)]
    late = {"kind": "face_reaction", "start": 11.0, "end": 12.0, "score": 92}
    early = dict(late, start=10.4)
    baseline = moments_module._opening_score(10.0, words, {}, {})
    assert moments_module._opening_score(10.0, words, {}, {"events": [late]}) == baseline
    assert moments_module._opening_score(10.0, words, {}, {"events": [early]}) == 92
    assert moments_module._opening_score(10.0, words, {}, {"events": [dict(early, kind="scene_cut")]}) == baseline
    assert moments_module._opening_score(11.0, words, {}, {}) > baseline


def test_fast_question_and_reply_are_separate_cut_points():
    segments = [{"words": [word("¿Quién?", 0, 0.3), word("¡Yo!", 0.31, 0.58)]}]
    assert [s["text"] for s in build_sentences(segments)] == ["¿Quién?", "¡Yo!"]


def test_direct_question_can_open_after_a_quick_mic_check():
    segments = [{"words": [word("Probando", 0, 0.3), word("audio.", 0.3, 0.55),
                           word("¿Quién", 0.55, 0.85), word("ganó?", 0.86, 1.2)]}]
    intro, hook = build_sentences(segments)
    assert hook["start"] == 0.55
    score = moments_module._opening_score
    assert score(hook["start"], hook["words"], {}, {}) > score(0, intro["words"], {}, {})

@pytest.mark.parametrize("picks,expected", [
    ([{"id": 1, "hook": "Si fallo", "payoff": "ganamos la partida"}], [65, 68]),
    ([{"id": 1, "hook": "Ganamos", "payoff": "ganamos la partida"}], [65, 60]),
    ([{"id": 1, "hook": "si fallo", "payoff": "perdimos la partida"}], [65, 60]),
    ([{"id": True, "hook": "si fallo", "payoff": "ganamos la partida"}], [65, 60]),
    (None, [65, 60]),
])
def test_local_review_requires_grounded_opening_and_payoff(monkeypatch, picks, expected):
    pool = [
        {"start": 0, "end": 20, "score": 65, "text": "hola chat", "score_breakdown": {"total": 65}},
        {"start": 90, "end": 110, "score": 60, "text": "si fallo perdemos", "score_breakdown": {"total": 60}},
    ]
    segments = [{"words": [
        word("Hola", 0.1, 0.5), word("chat", 2, 2.5),
        word("Si", 90.1, 90.25), word("fallo,", 90.3, 90.8), word("perdemos.", 91, 91.5),
        word("¡Ganamos", 102, 102.3), word("la", 102.4, 102.6), word("partida!", 103, 103.6),
    ]}]
    calls = []
    def review(messages):
        calls.append(messages)
        return {"picks": picks + picks} if picks is not None else None
    monkeypatch.setattr(moments_module, "_llm_call", review)
    moments_module._review_shortlist(pool, moments_module._WordIndex(segments))
    assert len(calls) == 1
    assert [c["score"] for c in pool] == expected
    assert [c["score_breakdown"]["total"] for c in pool] == expected


def test_stakes_outscore_an_ordinary_chat_greeting():
    assert moments_module._spoken_opening("Si fallo") >= 68
    assert moments_module._spoken_opening("chat me reta") >= 68
    assert moments_module._spoken_opening("hola chat") < 68
