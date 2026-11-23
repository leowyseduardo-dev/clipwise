from __future__ import annotations

import re

from app.subtitles import build_ass, build_cues, cues_to_srt, rebuild_edited_cues


def word(text: str, start: float, end: float) -> dict[str, object]:
    return {"w": text, "start": start, "end": end, "p": 1.0}


def test_build_cues_splits_on_gap_and_sentence_end() -> None:
    words = [
        word("Hola", 0.0, 0.4),
        word("mundo.", 0.45, 0.9),
        word("Esto", 1.6, 2.0),
        word("es", 2.05, 2.2),
        word("otra", 2.25, 2.5),
        word("frase.", 2.55, 2.9),
    ]

    cues = build_cues(words, "bold")

    assert len(cues) == 2
    assert cues[0]["text"] == "Hola mundo."
    assert cues[1]["text"] == "Esto es otra frase."
    assert cues[0]["start"] == 0.0
    assert cues[1]["end"] == 2.9


def test_build_cues_respects_max_words_per_style() -> None:
    words = [word(f"palabra{i}", i * 0.3, i * 0.3 + 0.25) for i in range(9)]

    bold = build_cues(words, "bold")
    minimal = build_cues(words, "minimal")
    shorts = build_cues(words, "shorts")

    assert all(len(cue["words"]) <= 4 for cue in bold)
    assert all(len(cue["words"]) <= 7 for cue in minimal)
    assert all(len(cue["words"]) == 1 for cue in shorts)
    assert sum(len(cue["words"]) for cue in bold) == 9
    assert sum(len(cue["words"]) for cue in shorts) == 9


def test_build_ass_has_header_and_one_event_per_word() -> None:
    cues = [
        {
            "start": 0.0,
            "end": 1.0,
            "text": "Hola mundo",
            "words": [word("Hola", 0.0, 0.5), word("mundo", 0.5, 1.0)],
        }
    ]

    ass = build_ass(cues, "neon")

    assert "PlayResX: 1080" in ass
    assert "PlayResY: 1920" in ass
    events = [line for line in ass.splitlines() if line.startswith("Dialogue:")]
    assert len(events) == 2
    assert "&H00EED322" in events[0]
    assert events[0].startswith("Dialogue: 0,0:00:00.00,0:00:00.50")


def test_build_ass_time_map_and_duration_clip() -> None:
    cues = [
        {
            "start": 3.0,
            "end": 5.0,
            "text": "Uno dos",
            "words": [word("Uno", 3.0, 4.0), word("dos", 4.0, 5.0)],
        }
    ]

    ass = build_ass(cues, "clean", time_map=lambda value: max(0.0, value - 2.0), duration=3.0)
    events = [line for line in ass.splitlines() if line.startswith("Dialogue:")]

    assert len(events) == 2
    assert events[0].startswith("Dialogue: 0,0:00:01.00,")
    # The second word starts at 2 s and the cue is limited to 3 s.
    assert "0:00:02.00,0:00:03.00" in events[1]


def test_build_ass_skips_words_beyond_duration() -> None:
    cues = [
        {
            "start": 5.0,
            "end": 7.0,
            "text": "Tarde",
            "words": [word("Tarde", 5.0, 7.0)],
        }
    ]

    ass = build_ass(cues, "bold", duration=3.0)
    assert not [line for line in ass.splitlines() if line.startswith("Dialogue:")]


def test_cues_to_srt_applies_time_map() -> None:
    cues = [{"start": 10.0, "end": 12.0, "text": "Hola desde el clip"}]

    srt = cues_to_srt(cues, time_map=lambda value: max(0.0, value - 2.0))

    assert "1\n00:00:08,000 --> 00:00:10,000\nHola desde el clip" in srt


def test_rebuild_edited_cues_clamps_and_rebuilds_words() -> None:
    rebuilt = rebuild_edited_cues(
        [
            {"start": -2.0, "end": 2.0, "text": "  Hola   mundo  "},
            {"start": 0.5, "end": 1.0, "text": "   "},
            {"start": 3.0, "end": 3.0, "text": "Corto"},
        ],
        duration=2.0,
    )

    assert len(rebuilt) == 1
    cue = rebuilt[0]
    assert cue["start"] == 0.0
    assert cue["end"] == 2.0
    assert cue["text"] == "Hola mundo"
    assert len(cue["words"]) == 2
    assert cue["words"][0]["start"] == 0.0
    assert abs(cue["words"][-1]["end"] - 2.0) < 0.01
    for item in cue["words"]:
        assert 0.0 <= item["start"] <= item["end"] <= 2.05


def test_cues_to_srt_drops_empty_and_reversed_cues() -> None:
    srt = cues_to_srt(
        [
            {"start": 1.0, "end": 1.0, "text": "sin duracion"},
            {"start": 2.0, "end": 3.0, "text": "  "},
            {"start": 4.0, "end": 5.0, "text": "valido"},
        ]
    )

    assert "valido" in srt
    assert "sin duracion" not in srt
    assert srt.startswith("1\n00:00:04,000")


def test_build_ass_shorts_is_uppercase_with_emphasis_and_animation() -> None:
    cues = [
        {
            "start": 0.0,
            "end": 0.4,
            "text": "full",
            "words": [word("full", 0.0, 0.4)],
        },
        {
            "start": 0.5,
            "end": 0.9,
            "text": "momento",
            "words": [word("momento", 0.5, 0.9)],
        },
    ]

    ass = build_ass(cues, "shorts", duration=2.0)
    events = [line for line in ass.splitlines() if line.startswith("Dialogue:")]

    assert "Style: Clip,Arial Black,126" in ass
    assert len(events) == 2
    assert "FULL" in events[0]
    assert "MOMENTO" in events[1]
    assert "\\an5" in events[0]
    assert "\\pos(540,1536)" in events[0]
    assert "\\fad(50,35)" in events[0]
    assert "\\fscx112" in events[0]
    assert "\\1c&H0000D7FF" in events[0]
    assert "\\1c&H00FFFFFF" in events[1]


def test_build_ass_shorts_scales_long_words_to_fit() -> None:
    cues = [
        {
            "start": 0.0,
            "end": 1.0,
            "text": "extraordinario",
            "words": [word("extraordinario", 0.0, 1.0)],
        }
    ]

    ass = build_ass(cues, "shorts", duration=2.0)
    event = next(line for line in ass.splitlines() if line.startswith("Dialogue:"))
    size = int(re.search(r"\\fs(\d+)", event).group(1))

    assert 58 <= size < 126
    assert "EXTRAORDINARIO" in event


def test_build_ass_shorts_holds_each_word_until_the_next_one() -> None:
    cues = [
        {
            "start": 0.0,
            "end": 0.3,
            "text": "uno",
            "words": [word("uno", 0.0, 0.3)],
        },
        {
            "start": 0.35,
            "end": 0.7,
            "text": "dos",
            "words": [word("dos", 0.35, 0.7)],
        },
    ]

    ass = build_ass(cues, "shorts", duration=2.0)
    events = [line for line in ass.splitlines() if line.startswith("Dialogue:")]

    assert len(events) == 2
    assert "0:00:00.00,0:00:00.35" in events[0]
    assert "0:00:00.35,0:00:00.90" in events[1]


def test_build_ass_overlay_shows_context_without_channel_or_game_label() -> None:
    ass = build_ass(
        [],
        "shorts",
        duration=6.0,
        overlay={
            "kicker": "DR DONUT · ROBLOX",
            "context": "NUEVO EFECTO DE PULLS",
            "is_gaming": True,
            "context_seconds": 5.5,
        },
        top_offset=640,
    )
    events = [line for line in ass.splitlines() if line.startswith("Dialogue:")]

    assert "Style: Overlay" in ass
    assert len(events) == 1
    assert events[0].startswith("Dialogue: 0,0:00:00.00,0:00:05.50,Overlay")
    assert "\\pos(540,748)" in events[0]
    assert "NUEVO EFECTO DE PULLS" in events[0]
    assert "DR DONUT" not in ass
    assert "ROBLOX" not in ass


def test_build_ass_without_overlay_has_no_overlay_events() -> None:
    ass = build_ass([], "shorts", duration=6.0)

    assert "Style: Overlay" in ass
    assert not [line for line in ass.splitlines() if line.startswith("Dialogue:")]


def test_build_ass_impact_uses_impact_font_and_yellow_emphasis() -> None:
    cues = [
        {
            "start": 0.0,
            "end": 1.0,
            "text": "esto es brutal",
            "words": [
                word("esto", 0.0, 0.3),
                word("es", 0.3, 0.6),
                word("brutal", 0.6, 1.0),
            ],
        }
    ]

    ass = build_ass(cues, "impact", duration=2.0)
    style = next(line for line in ass.splitlines() if line.startswith("Style: Clip,"))
    events = [line for line in ass.splitlines() if line.startswith("Dialogue:")]

    assert "Style: Clip,Impact,132" in ass
    assert "&H00FFFFFF" in style
    assert len(events) == 3
    assert "BRUTAL" in events[2].upper()


def test_build_ass_pill_uses_box_border_style() -> None:
    cues = [
        {
            "start": 0.0,
            "end": 1.0,
            "text": "pill",
            "words": [word("pill", 0.0, 1.0)],
        }
    ]

    ass = build_ass(cues, "pill", duration=2.0)
    style = next(line for line in ass.splitlines() if line.startswith("Style: Clip,"))
    event = next(line for line in ass.splitlines() if line.startswith("Dialogue:"))

    assert ",3,16,0,5,60,60,0,1" in style
    assert "&H00F2F2F2" in style
    assert "\\pos(540,1536)" in event


def test_build_ass_box_and_yellow_have_their_own_look() -> None:
    cues = [
        {
            "start": 0.0,
            "end": 1.0,
            "text": "caja",
            "words": [word("caja", 0.0, 1.0)],
        }
    ]

    box = build_ass(cues, "box", duration=2.0)
    yellow = build_ass(cues, "yellow", duration=2.0)

    assert ",3,14,0,2,60,60,380,1" in box
    assert "&HB4000000" in box
    assert "Style: Clip," in yellow
    assert ",76," in yellow
    assert "&H0000E5FF" in next(
        line for line in yellow.splitlines() if line.startswith("Style: Clip,")
    )


def test_build_ass_anchor_y_moves_captions_above_the_panels() -> None:
    cues = [
        {
            "start": 0.0,
            "end": 0.4,
            "text": "uno",
            "words": [word("uno", 0.0, 0.4)],
        }
    ]

    one_word = build_ass(cues, "shorts", duration=2.0, anchor_y=786)
    multi = build_ass(cues, "bold", duration=2.0, anchor_y=786)

    assert "\\pos(540,786)" in next(
        line for line in one_word.splitlines() if line.startswith("Dialogue:")
    )
    assert "\\an5\\pos(540,786)" in next(
        line for line in multi.splitlines() if line.startswith("Dialogue:")
    )


def test_build_ass_title_card_burns_the_opening_hook() -> None:
    ass = build_ass(
        [],
        "impact",
        duration=8.0,
        title_card={
            "text": "no se lo esperaba",
            "seconds": 4.0,
            "position": "top",
            "style": "impact",
        },
    )
    events = [line for line in ass.splitlines() if line.startswith("Dialogue:")]

    assert "Style: Rotulo,Impact,84" in ass
    assert len(events) == 1
    assert events[0].startswith("Dialogue: 0,0:00:00.00,0:00:04.00,Rotulo")
    assert "\\pos(540,230)" in events[0]
    assert "NO SE LO ESPERABA" in events[0]
    assert "\\fad(100,180)" in events[0]


def test_build_ass_title_card_box_style_and_wrap() -> None:
    ass = build_ass(
        [],
        "shorts",
        duration=10.0,
        title_card={
            "text": "un titulo bastante largo que necesita dos lineas para entrar",
            "seconds": 30.0,
            "position": "bottom",
            "style": "box",
        },
        anchor_y=900,
    )
    event = next(line for line in ass.splitlines() if line.startswith("Dialogue:"))

    assert event.startswith("Dialogue: 0,0:00:00.00,0:00:10.00,RotuloBox")
    assert "\\pos(540,1520)" in event
    assert "\\N" in event
    assert "Style: RotuloBox,Arial,58" in ass


def test_build_ass_empty_title_card_adds_nothing() -> None:
    ass = build_ass([], "shorts", duration=4.0, title_card={"text": "   "})

    assert not [line for line in ass.splitlines() if line.startswith("Dialogue:")]
