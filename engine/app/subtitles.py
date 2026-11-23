from __future__ import annotations

import re
from typing import Any, Callable

from .config import settings
from .utils import clamp, fmt_ass_time, fmt_srt_time

_STYLE_CONFIG: dict[str, dict[str, Any]] = {
    "shorts": {
        "font": "Arial Black",
        "size": 126,
        "primary": "&H00FFFFFF",
        "accent": "&H0000D7FF",
        "outline": 9,
        "shadow": 2,
        "margin_v": 0,
        "max_words": 1,
        "max_chars": 18,
        "one_word": True,
        "uppercase": True,
        "anchor_y": 1536,
        "alignment": 5,
        "target_width": 0.88,
        "pop": True,
    },
    "bold": {
        "size": 78,
        "primary": "&H00FFFFFF",
        "accent": "&H004DE1FF",
        "outline": 5,
        "shadow": 1,
        "margin_v": 420,
        "max_words": 4,
        "max_chars": 24,
    },
    "clean": {
        "size": 62,
        "primary": "&H00FFFFFF",
        "accent": "&H00FA8BA7",
        "outline": 3,
        "shadow": 1,
        "margin_v": 360,
        "max_words": 5,
        "max_chars": 32,
    },
    "neon": {
        "size": 70,
        "primary": "&H00FFFFFF",
        "accent": "&H00EED322",
        "outline": 4,
        "shadow": 2,
        "margin_v": 420,
        "max_words": 4,
        "max_chars": 26,
    },
    "minimal": {
        "size": 54,
        "primary": "&H00F2F2F2",
        "accent": "&H0047E0FD",
        "outline": 2,
        "shadow": 0,
        "margin_v": 320,
        "max_words": 7,
        "max_chars": 46,
    },
    # Ported from ViroCut's caption presets.
    "impact": {
        "font": "Impact",
        "size": 132,
        "primary": "&H00FFFFFF",
        "accent": "&H0000E5FF",
        "outline": 9,
        "shadow": 0,
        "margin_v": 360,
        "max_words": 2,
        "max_chars": 22,
        "uppercase": True,
    },
    "pill": {
        "size": 68,
        "primary": "&H00000000",
        "accent": "&H00000000",
        "outline": 16,
        "outline_colour": "&H00F2F2F2",
        "border_style": 3,
        "shadow": 0,
        "margin_v": 0,
        "max_words": 1,
        "max_chars": 20,
        "one_word": True,
        "uppercase": False,
        "anchor_y": 1536,
        "alignment": 5,
        "pop": True,
    },
    "box": {
        "size": 62,
        "primary": "&H00FFFFFF",
        "accent": "&H0000E5FF",
        "outline": 14,
        "outline_colour": "&HB4000000",
        "border_style": 3,
        "shadow": 0,
        "margin_v": 380,
        "max_words": 4,
        "max_chars": 28,
    },
    "yellow": {
        "size": 76,
        "primary": "&H0000E5FF",
        "accent": "&H00FFFFFF",
        "outline": 6,
        "shadow": 1,
        "margin_v": 380,
        "max_words": 3,
        "max_chars": 26,
        "uppercase": True,
    },
}

_TITLE_CARD_STYLES: dict[str, dict[str, Any]] = {
    "impact": {
        "font": "Impact",
        "size": 84,
        "primary": "&H00FFFFFF",
        "outline_colour": "&H00000000",
        "outline": 8,
        "uppercase": True,
        "border_style": 1,
    },
    "clean": {
        "font": "Arial",
        "size": 62,
        "primary": "&H00FFFFFF",
        "outline_colour": "&H00000000",
        "outline": 5,
        "uppercase": False,
        "border_style": 1,
    },
    "box": {
        "font": "Arial",
        "size": 58,
        "primary": "&H00FFFFFF",
        "outline_colour": "&HB4000000",
        "outline": 18,
        "uppercase": False,
        "border_style": 3,
    },
}

_TITLE_CARD_Y = {"top": 230, "center": 960, "bottom": 1520}

SentenceEnd = re.compile(r"[.!?…][\"')\]]?$")

_EMPHASIS_WORDS = frozenset(
    {
        "full",
        "max",
        "now",
        "here",
        "only",
        "everything",
        "never",
        "always",
        "best",
        "worst",
        "free",
        "money",
        "secret",
        "nobody",
        "you",
        "mine",
        "no",
        "yes",
        "wait",
        "look",
        "stop",
        "go",
        "new",
        "first",
        "last",
        "huge",
        "crazy",
        "insane",
        "broken",
        "impossible",
        "real",
        "shiny",
        "moment",
        "million",
        "billion",
        "todo",
        "nada",
        "nunca",
        "siempre",
        "ahora",
        "aqui",
        "aquí",
        "solo",
        "sólo",
        "mejor",
        "peor",
        "gratis",
        "dinero",
        "secreto",
        "nadie",
        "tu",
        "tú",
        "yo",
        "espera",
        "mira",
        "para",
        "primero",
        "último",
        "ultimo",
        "locura",
        "increible",
        "increíble",
        "imposible",
        "real",
        "brutal",
        "millones",
        "mil",
    }
)


def _style(style: str) -> dict[str, Any]:
    return _STYLE_CONFIG.get(style, _STYLE_CONFIG["bold"])


def _token_key(token: str) -> str:
    return token.strip(" \t\r\n.,!?¿¡…;:\"'()[]{}").lower()


def _is_emphasis(token: str) -> bool:
    if not token:
        return False
    if "!" in token or "¡" in token or any(char.isdigit() for char in token):
        return True
    return _token_key(token) in _EMPHASIS_WORDS


def _fit_font_size(token: str, config: dict[str, Any]) -> int:
    base = int(config["size"])
    target = float(settings.target_w) * float(config.get("target_width", 0.88))
    units = 0.0
    for char in token:
        units += 0.72 if char.isalnum() else 0.42
    estimated = max(1.0, units) * base
    if estimated <= target:
        return base
    return max(58, min(base, int(target / max(1.0, units))))


def _one_word_prefix(
    token: str,
    config: dict[str, Any],
    anchor_y: int | None = None,
) -> str:
    anchor = int(config.get("anchor_y", 1536)) if anchor_y is None else int(anchor_y)
    size = _fit_font_size(token, config)
    parts = [
        "\\an5",
        f"\\pos({settings.target_w // 2},{anchor})",
        f"\\fs{size}",
        "\\fad(50,35)",
    ]
    if config.get("pop"):
        parts.extend(["\\fscx112", "\\fscy112", "\\t(0,70,\\fscx100\\fscy100)"])
    return "{" + "".join(parts) + "}"


def _escape(text: str) -> str:
    cleaned = (
        text.replace("\\", "/")
        .replace("{", "(")
        .replace("}", ")")
        .replace("\r", " ")
        .replace("\n", " ")
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or "…"


def _even_words(text: str, start: float, end: float) -> list[dict[str, Any]]:
    tokens = [token for token in text.split() if token]
    if not tokens:
        return []
    weights = [len(token) + 1 for token in tokens]
    total = float(sum(weights))
    duration = max(0.3, end - start)
    cursor = start
    words: list[dict[str, Any]] = []
    for token, weight in zip(tokens, weights):
        span = duration * weight / total
        words.append(
            {
                "w": token,
                "start": round(cursor, 3),
                "end": round(max(cursor + 0.05, cursor + span), 3),
                "p": 1.0,
            }
        )
        cursor += span
    words[-1]["end"] = round(max(words[-1]["start"] + 0.05, end), 3)
    return words


def build_cues(words: list[dict[str, Any]], style: str = "bold") -> list[dict[str, Any]]:
    config = _style(style)
    ordered = sorted(words, key=lambda item: float(item.get("start", 0.0)))
    cues: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []

    def flush() -> None:
        if not current:
            return
        text = " ".join(str(word.get("w", "")).strip() for word in current).strip()
        if text:
            cues.append(
                {
                    "start": round(float(current[0]["start"]), 3),
                    "end": round(float(current[-1]["end"]), 3),
                    "text": text,
                    "words": [dict(word) for word in current],
                }
            )
        current.clear()

    for word in ordered:
        token = str(word.get("w", "")).strip()
        if not token:
            continue
        if current:
            gap = float(word.get("start", 0.0)) - float(current[-1].get("end", 0.0))
            prospective = " ".join([str(item.get("w", "")) for item in current] + [token])
            if (
                gap > 0.45
                or len(current) >= int(config["max_words"])
                or len(prospective) > int(config["max_chars"])
            ):
                flush()
        current.append(dict(word, w=token))
        if len(current) >= 2 and SentenceEnd.search(token):
            flush()
    flush()
    return cues


def rebuild_edited_cues(cues: list[dict[str, Any]], duration: float) -> list[dict[str, Any]]:
    rebuilt: list[dict[str, Any]] = []
    for cue in cues:
        start = clamp(float(cue.get("start", 0.0)), 0.0, max(0.0, duration))
        end = clamp(float(cue.get("end", start + 0.5)), start, max(0.0, duration))
        if end - start < 0.3:
            end = min(max(0.0, duration), start + 0.3)
        text = re.sub(r"\s+", " ", str(cue.get("text", ""))).strip()
        if not text or end <= start:
            continue
        words = _even_words(text, start, end)
        if not words:
            continue
        rebuilt.append(
            {
                "start": round(start, 3),
                "end": round(end, 3),
                "text": text,
                "words": words,
            }
        )
    return rebuilt


def _break_index(tokens: list[str]) -> int | None:
    total = sum(len(token) + 1 for token in tokens)
    if total <= 26 or len(tokens) < 4:
        return None
    midpoint = total / 2.0
    cursor = 0
    for index, token in enumerate(tokens[:-1]):
        cursor += len(token) + 1
        if cursor >= midpoint:
            return index
    return None


def _map_cue_words(
    cue: dict[str, Any],
    time_map: Callable[[float], float] | None,
    duration: float | None,
) -> tuple[list[dict[str, Any]], float]:
    mapped: list[dict[str, Any]] = []
    for word in cue.get("words") or []:
        token = _escape(str(word.get("w", "")))
        start = float(word.get("start", cue.get("start", 0.0)))
        end = float(word.get("end", start + 0.2))
        if time_map:
            start = time_map(start)
            end = time_map(end)
        if duration is not None:
            if start >= duration - 0.02:
                continue
            end = min(end, duration)
        if end <= start:
            end = start + 0.05
        mapped.append({"w": token, "start": start, "end": end})
    if not mapped:
        return [], 0.0
    cue_end = float(cue.get("end", mapped[-1]["end"]))
    if time_map:
        cue_end = time_map(cue_end)
    if duration is not None:
        cue_end = min(cue_end, duration)
    if cue_end <= mapped[-1]["start"]:
        cue_end = mapped[-1]["end"] + 0.1
    return mapped, cue_end


def _overlay_events(
    overlay: dict[str, Any] | None,
    *,
    top_offset: int,
    duration: float | None,
) -> list[str]:
    if not overlay:
        return []
    total = max(1.0, float(duration or 6.0))
    context = _escape(str(overlay.get("context") or "")).strip()
    events: list[str] = []
    if context and context != "…":
        end = max(
            0.8,
            min(
                total,
                float(
                    overlay.get("context_seconds")
                    or settings.overlay_context_seconds
                ),
            ),
        )
        events.append(
            f"Dialogue: 0,0:00:00.00,{fmt_ass_time(end)},Overlay,,0,0,0,,"
            f"{{\\an8\\pos(540,{top_offset + 108})\\fs54\\bord7\\shad2"
            f"\\1c&H00FFFFFF\\fad(100,220)\\fscx108\\fscy108"
            f"\\t(0,140,\\fscx100\\fscy100)}}{context}"
        )
    return events


def _wrap_card(text: str, limit: int = 34) -> str:
    if len(text) <= limit:
        return text
    words = text.split()
    best_index = 1
    best_delta = 10**9
    for index in range(1, len(words)):
        left = len(" ".join(words[:index]))
        right = len(" ".join(words[index:]))
        delta = abs(left - right)
        if delta < best_delta:
            best_delta = delta
            best_index = index
    return " ".join(words[:best_index]) + "\\N" + " ".join(words[best_index:])


def _title_card_events(
    card: dict[str, Any] | None,
    *,
    duration: float | None,
) -> list[str]:
    """Opening title card: the hook line ViroCut burns into the first seconds."""
    if not card:
        return []
    text = _escape(str(card.get("text") or "")).strip()
    if not text or text == "…":
        return []
    style = str(card.get("style") or "impact")
    config = _TITLE_CARD_STYLES.get(style, _TITLE_CARD_STYLES["impact"])
    seconds = float(card.get("seconds") or 4.0)
    seconds = max(0.6, min(seconds, max(0.6, float(duration or 6.0))))
    position = str(card.get("position") or "top")
    y = _TITLE_CARD_Y.get(position, _TITLE_CARD_Y["top"])
    if config.get("uppercase"):
        text = text.upper()
    text = _wrap_card(text)
    style_name = {"box": "RotuloBox", "clean": "RotuloClean"}.get(style, "Rotulo")
    return [
        (
            f"Dialogue: 0,0:00:00.00,{fmt_ass_time(seconds)},{style_name},,0,0,0,,"
            f"{{\\an5\\pos(540,{y})\\fs{config['size']}\\bord{config['outline']}"
            f"\\shad0\\1c{config['primary']}\\3c{config['outline_colour']}"
            f"\\fad(100,180)\\fscx106\\fscy106\\t(0,120,\\fscx100\\fscy100)}}{text}"
        )
    ]


def build_ass(
    cues: list[dict[str, Any]],
    style: str = "bold",
    *,
    time_map: Callable[[float], float] | None = None,
    duration: float | None = None,
    font: str | None = None,
    overlay: dict[str, Any] | None = None,
    top_offset: int = 0,
    anchor_y: int | None = None,
    title_card: dict[str, Any] | None = None,
    colors: tuple[str | None, str | None] = (None, None),
    script_width: int = 1080,
    brand_text: str = "",
) -> str:
    config = dict(_style(style))
    for key, value in zip(("primary", "accent"), colors):
        if value and re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            config[key] = "&H00" + value[5:7] + value[3:5] + value[1:3]
    font_name = font or config.get("font") or settings.subtitle_font
    alignment = int(config.get("alignment", 2))
    border_style = int(config.get("border_style", 1))
    outline_colour = str(config.get("outline_colour") or "&H00000000")
    header = [
        "[Script Info]",
        "; Generado por Clipwise AI",
        "ScriptType: v4.00+",
        f"PlayResX: {script_width}",
        "PlayResY: 1920",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        (
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
            "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
            "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding"
        ),
        (
            f"Style: Clip,{font_name},{config['size']},{config['primary']},"
            f"{config['primary']},{outline_colour},&H00000000,-1,0,0,0,100,100,0,0,"
            f"{border_style},{config['outline']},{config['shadow']},{alignment},60,60,"
            f"{config['margin_v']},1"
        ),
        (
            f"Style: Overlay,{font_name},54,&H00FFFFFF,&H00FFFFFF,&H00000000,"
            "&H64000000,-1,0,0,0,100,100,0,0,1,6,2,7,40,40,0,1"
        ),
        (
            "Style: Rotulo,Impact,84,&H00FFFFFF,&H00FFFFFF,&H00000000,"
            "&H64000000,-1,0,0,0,100,100,0,0,1,8,0,5,40,40,0,1"
        ),
        (
            "Style: RotuloClean,Arial,62,&H00FFFFFF,&H00FFFFFF,&H00000000,"
            "&H64000000,-1,0,0,0,100,100,0,0,1,5,0,5,40,40,0,1"
        ),
        (
            "Style: RotuloBox,Arial,58,&H00FFFFFF,&H00FFFFFF,&HB4000000,"
            "&H00000000,-1,0,0,0,100,100,0,0,3,18,0,5,40,40,0,1"
        ),
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    events: list[str] = []
    overlay_data = overlay
    if title_card and str(title_card.get("text") or "").strip() and overlay:
        # A custom opening card replaces the automatic context line.
        overlay_data = {**overlay, "context": ""}
    events.extend(_overlay_events(overlay_data, top_offset=top_offset, duration=duration))
    events.extend(_title_card_events(title_card, duration=duration))

    if brand_text and duration:
        events.append(f"Dialogue: 1,0:00:00.00,{fmt_ass_time(duration)},Overlay,,0,0,0,,"
                      f"{{\\an7\\pos(60,110)\\fs42\\bord3}}{_escape(brand_text)}")

    def compose():
        # Positions are authored on the original 1080-wide template. Broader
        # formats keep glyph proportions and center the text in their safe area.
        centered = (event.replace(r"\pos(540,", rf"\pos({script_width // 2},", 1)
                    for event in events)
        return "\n".join([*header, *centered]) + "\n"

    if config.get("one_word"):
        words: list[dict[str, Any]] = []
        for cue in cues:
            mapped, _ = _map_cue_words(cue, time_map, duration)
            words.extend(mapped)
        words.sort(key=lambda item: item["start"])
        for index, active in enumerate(words):
            event_start = active["start"]
            next_start = (
                words[index + 1]["start"] if index < len(words) - 1 else None
            )
            if next_start is not None:
                event_end = min(next_start, active["end"] + 0.35)
            else:
                event_end = active["end"] + 0.20
            if duration is not None:
                event_end = min(event_end, duration)
            event_end = max(event_end, event_start + 0.08)
            token = active["w"].upper() if config.get("uppercase") else active["w"]
            color = (
                config["accent"]
                if _is_emphasis(active["w"])
                else config["primary"]
            )
            prefix = _one_word_prefix(token, config, anchor_y)
            events.append(
                f"Dialogue: 0,{fmt_ass_time(event_start)},{fmt_ass_time(event_end)},"
                f"Clip,,0,0,0,,{prefix}{{\\1c{color}}}{token}"
            )
        return compose()

    for cue in cues:
        mapped, cue_end = _map_cue_words(cue, time_map, duration)
        if not mapped:
            continue

        break_at = _break_index([word["w"] for word in mapped])
        for index, active in enumerate(mapped):
            event_start = active["start"]
            event_end = cue_end if index == len(mapped) - 1 else mapped[index + 1]["start"]
            if event_end <= event_start:
                event_end = max(active["end"], event_start + 0.05)
            parts: list[str] = []
            for other_index, word in enumerate(mapped):
                # Single-word cues (the usual case when a clip was built with
                # the one-word style) would otherwise leave every caption in
                # the accent colour: keep them white and reserve the accent
                # for words that actually carry emphasis.
                if len(mapped) == 1:
                    color = (
                        config["accent"]
                        if _is_emphasis(word["w"])
                        else config["primary"]
                    )
                else:
                    color = config["accent"] if other_index == index else config["primary"]
                parts.append(f"{{\\1c{color}}}{word['w']}")
                if break_at is not None and other_index == break_at:
                    parts.append("\\N")
            line = " ".join(parts)
            prefix = ""
            fade = r"\fad(40,0)" if index == 0 else ""
            if anchor_y is not None:
                prefix = f"{{\\an5\\pos(540,{int(anchor_y)}){fade}}}"
            elif fade:
                prefix = "{" + fade + "}"
            events.append(
                f"Dialogue: 0,{fmt_ass_time(event_start)},{fmt_ass_time(event_end)},"
                f"Clip,,0,0,0,,{prefix}{line}"
            )

    return compose()


def cues_to_srt(
    cues: list[dict[str, Any]],
    *,
    time_map: Callable[[float], float] | None = None,
    duration: float | None = None,
) -> str:
    blocks: list[str] = []
    index = 1
    for cue in cues:
        start = float(cue.get("start", 0.0))
        end = float(cue.get("end", start + 0.5))
        if time_map:
            start = time_map(start)
            end = time_map(end)
        if duration is not None:
            start = min(start, duration)
            end = min(end, duration)
        if end <= start:
            continue
        text = str(cue.get("text", "")).strip()
        if not text:
            continue
        blocks.append(
            f"{index}\n{fmt_srt_time(start)} --> {fmt_srt_time(end)}\n{text}\n"
        )
        index += 1
    return "\n".join(blocks)
