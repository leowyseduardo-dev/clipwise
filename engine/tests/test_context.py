from __future__ import annotations

from app.context import (
    build_overlay,
    detect_game,
    enrich_source_meta,
    merge_source_meta,
    source_meta_from_info,
    source_meta_from_upload,
)


def test_detect_game_matches_specific_alias() -> None:
    assert detect_game("Nuevo parche de GTA 5") == "Grand Theft Auto V"
    assert detect_game("Minecraft speedrun en directo") == "Minecraft"
    assert detect_game("Roblox pero es un caos") == "Roblox"
    assert detect_game("Receta de pasta con tomate") == ""


def test_source_meta_from_info_cleans_streamer_and_detects_game() -> None:
    meta = source_meta_from_info(
        {
            "title": "DR DONUT: NEW PULLS EFFECT (Roblox)",
            "description": "Gameplay de Roblox con pulls nuevos.",
            "channel": "Dr Donut - Topic",
            "uploader": "Dr Donut",
            "tags": ["Roblox", "Gameplay"],
            "categories": ["Gaming"],
            "duration": 5400,
            "width": 1920,
            "height": 1080,
            "fps": 60,
            "webpage_url": "https://www.youtube.com/watch?v=abc",
        }
    )

    assert meta["streamer"] == "Dr Donut"
    assert meta["channel"] == "Dr Donut"
    assert meta["game"] == "Roblox"
    assert meta["is_gaming"] is True
    assert meta["title"].startswith("DR DONUT")


def test_build_overlay_strips_streamer_and_game_from_context() -> None:
    meta = {
        "streamer": "Dr Donut",
        "channel": "Dr Donut",
        "game": "Roblox",
        "is_gaming": True,
    }

    overlay = build_overlay(
        meta,
        {"title": "NUEVO EFECTO DE PULLS EN ROBLOX"},
    )

    assert overlay["kicker"] == ""
    assert overlay["context"] == "NUEVO EFECTO DE PULLS"
    assert overlay["is_gaming"] is True
    assert overlay["context_seconds"] >= 4.0


def test_build_overlay_does_not_add_game_or_channel_filler() -> None:
    overlay = build_overlay(
        {"streamer": "Dr Donut", "game": "Roblox", "is_gaming": True},
        {"title": "Momento destacado", "hook": "Clip seleccionado."},
    )

    assert overlay["context"] == ""
    assert overlay["kicker"] == ""


def test_build_overlay_ignores_visual_fallback_hook() -> None:
    overlay = build_overlay(
        {"streamer": "Dr Donut", "game": "Roblox", "is_gaming": True},
        {
            "title": "Momento destacado",
            "hook": "Fragmento seleccionado por analisis visual.",
        },
    )

    assert overlay["context"] == ""


def test_merge_source_meta_keeps_user_values() -> None:
    merged = merge_source_meta(
        {"streamer": "Canal propio", "game": "Minecraft"},
        {"streamer": "Otro canal", "game": "Roblox", "is_gaming": True},
    )

    assert merged["streamer"] == "Canal propio"
    assert merged["game"] == "Minecraft"
    assert merged["is_gaming"] is True


def test_source_meta_from_upload_reads_filename() -> None:
    meta = source_meta_from_upload(
        title="",
        filename="directo de Valorant ranked.mp4",
    )

    assert meta["game"] == "Valorant"
    assert meta["is_gaming"] is True


def test_enrich_source_meta_detects_game_from_transcript() -> None:
    meta = enrich_source_meta(
        {"streamer": "Dr Donut", "is_gaming": False},
        "Hoy jugamos un rato a Roblox y luego hablamos del chat.",
    )

    assert meta["game"] == "Roblox"
    assert meta["is_gaming"] is True
