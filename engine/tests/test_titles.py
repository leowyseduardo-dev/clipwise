from __future__ import annotations

from app.titles import build_clip_title, is_weak_title


def sentence(text: str) -> dict[str, str]:
    return {"text": text}


def test_title_uses_later_summary_not_opening_line() -> None:
    window = [
        sentence("Bueno, pues hoy vamos a hablar de algo."),
        sentence("La mayoria comete el mismo error cuando empieza un negocio."),
        sentence("El problema no es el precio, es la falta de claridad."),
        sentence("Al final descubrio que el error estaba en el mensaje."),
    ]

    title = build_clip_title(window, language="es")

    assert not title.lower().startswith("bueno")
    assert title != window[0]["text"]
    assert any(
        keyword in title.lower()
        for keyword in ("error", "negocio", "precio", "claridad", "mensaje")
    )
    assert len(title) <= 72


def test_title_uses_context_that_only_appears_later() -> None:
    window = [
        sentence("Esto es una locura."),
        sentence("El secreto esta en el dinero."),
        sentence("Nadie te cuenta como funciona el sistema por dentro."),
    ]

    title = build_clip_title(window, language="es")

    assert "dinero" in title.lower() or "sistema" in title.lower()
    assert title != window[0]["text"]


def test_title_rejects_bare_question_and_keeps_body_conjunction() -> None:
    window = [
        sentence("¿Por qué?"),
        sentence("Nadie te cuenta cómo funciona el sistema por dentro."),
        sentence("¿Qué pasa cuando cambias el mensaje?"),
    ]

    title = build_clip_title(window, language="es")

    assert title != "¿Por qué?"
    assert title.startswith("¿")
    assert title.endswith("?")
    assert "cuando" in title
    assert "cuándo" not in title


def test_title_english_uses_claim_instead_of_opening() -> None:
    window = [
        sentence("Here is why that changes everything."),
        sentence("Most people make the same mistake when they start a business."),
        sentence("The problem is not the price, it is the lack of clarity."),
    ]

    title = build_clip_title(window, language="en")

    assert title != window[0]["text"]
    assert any(
        keyword in title.lower()
        for keyword in ("mistake", "business", "problem", "price", "clarity")
    )


def test_title_length_is_capped() -> None:
    window = [
        sentence(
            "Esta es una historia muy larga sobre un negocio que parece "
            "funcionar pero que en realidad tiene un problema enorme y "
            "muchas consecuencias que nadie quiere reconocer."
        )
    ]

    title = build_clip_title(window, language="es")

    assert 0 < len(title) <= 73
    assert not title.endswith(" ")


def test_title_meta_fallback_and_game_suffix() -> None:
    assert (
        build_clip_title(
            [],
            language="es",
            meta={"game": "Roblox", "streamer": "Dr Donut"},
        )
        == "El momento clave en Roblox"
    )

    title = build_clip_title(
        [sentence("El secreto del dinero que nadie te cuenta.")],
        language="es",
        meta={"game": "Roblox", "is_gaming": True},
    )

    assert "Roblox" in title
    assert len(title) <= 72


def test_is_weak_title_rejects_opening_sentence_and_stubs() -> None:
    first = "Here is why that changes everything."

    assert is_weak_title(first, first)
    assert is_weak_title("Por qué?", "¿Por qué?")
    assert is_weak_title("Momento destacado", "")
    assert not is_weak_title("Why that changes everything", first)

def test_garbled_transcript_never_becomes_a_title() -> None:
    from app.titles import _garble_penalty, _is_garbled, _is_looped, build_clip_title

    garbled = [
        {"text": "Tú eres imbecil, eres imbecil, pasándome, eres imbecil, pasándome"},
        {"text": "juga el cron 50 horas zorblok wexendo mirplen"},
    ]

    title = build_clip_title(garbled, language="es", meta={"source_title": "Directo de Roblox"})

    assert title
    assert "imbecil" not in title.lower()
    assert _is_garbled(garbled[1]["text"])
    assert _garble_penalty(garbled[1]["text"]) < 0.0
    assert _is_looped(garbled[0]["text"])


def test_clean_spanish_question_is_not_flagged_as_garbled() -> None:
    from app.titles import _is_garbled

    assert not _is_garbled("¿Qué pasa cuando cambias el mensaje?")
    assert not _is_garbled("Nadie te cuenta cómo funciona el sistema por dentro.")
