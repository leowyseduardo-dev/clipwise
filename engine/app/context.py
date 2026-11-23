from __future__ import annotations

import re
import unicodedata
from typing import Any

# Canonical name plus aliases. Keep aliases specific enough that ordinary
# conversation does not read as a game mention.
_GAME_LIBRARY: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Minecraft", ("minecraft", "mine craft")),
    ("Roblox", ("roblox", "ro blox")),
    ("Grand Theft Auto V", ("grand theft auto", "gta v", "gta 5", "gta online", "gta")),
    ("Fortnite", ("fortnite",)),
    ("Counter-Strike 2", ("counter strike", "counterstrike", "cs2", "csgo", "cs go")),
    ("Valorant", ("valorant",)),
    ("League of Legends", ("league of legends", "wild rift")),
    ("Dota 2", ("dota 2", "dota")),
    ("Overwatch 2", ("overwatch",)),
    ("Apex Legends", ("apex legends", "apex")),
    ("Call of Duty", ("call of duty", "warzone", "modern warfare", "black ops")),
    ("PUBG", ("pubg", "playerunknown")),
    ("Free Fire", ("free fire",)),
    ("Rocket League", ("rocket league",)),
    ("EA Sports FC", ("ea sports fc", "ea fc", "fifa")),
    ("NBA 2K", ("nba 2k",)),
    ("Madden NFL", ("madden",)),
    ("Rainbow Six Siege", ("rainbow six", "r6 siege", "rainbow 6")),
    ("Among Us", ("among us",)),
    ("Fall Guys", ("fall guys",)),
    ("Genshin Impact", ("genshin",)),
    ("Honkai: Star Rail", ("honkai",)),
    ("Elden Ring", ("elden ring",)),
    ("Dark Souls", ("dark souls",)),
    ("Bloodborne", ("bloodborne",)),
    ("Sekiro", ("sekiro",)),
    ("God of War", ("god of war",)),
    ("The Last of Us", ("last of us",)),
    ("Red Dead Redemption", ("red dead redemption", "red dead", "rdr2")),
    ("Cyberpunk 2077", ("cyberpunk 2077", "cyberpunk")),
    ("The Witcher 3", ("witcher 3", "the witcher", "witcher")),
    ("Skyrim", ("skyrim",)),
    ("World of Warcraft", ("world of warcraft",)),
    ("Final Fantasy XIV", ("final fantasy xiv", "final fantasy 14", "ffxiv", "final fantasy")),
    ("Diablo IV", ("diablo iv", "diablo 4", "diablo")),
    ("Path of Exile", ("path of exile",)),
    ("Baldur's Gate 3", ("baldur's gate", "baldurs gate")),
    ("Terraria", ("terraria",)),
    ("Stardew Valley", ("stardew valley", "stardew")),
    ("Animal Crossing", ("animal crossing",)),
    ("The Sims 4", ("the sims", "sims 4")),
    ("Dead by Daylight", ("dead by daylight",)),
    ("Phasmophobia", ("phasmophobia",)),
    ("Lethal Company", ("lethal company",)),
    ("Helldivers 2", ("helldivers",)),
    ("Palworld", ("palworld",)),
    ("ARK: Survival Evolved", ("ark survival", "ark ascended")),
    ("DayZ", ("dayz",)),
    ("Escape from Tarkov", ("escape from tarkov", "tarkov")),
    ("Hunt: Showdown", ("hunt showdown",)),
    ("Sea of Thieves", ("sea of thieves",)),
    ("Destiny 2", ("destiny 2", "destiny")),
    ("Warframe", ("warframe",)),
    ("Team Fortress 2", ("team fortress", "tf2")),
    ("Left 4 Dead", ("left 4 dead", "l4d")),
    ("Half-Life", ("half life", "halflife")),
    ("Doom", ("doom eternal", "doom")),
    ("Halo", ("halo infinite", "halo")),
    ("Forza Horizon", ("forza horizon", "forza")),
    ("Gran Turismo", ("gran turismo",)),
    ("Need for Speed", ("need for speed",)),
    ("Euro Truck Simulator", ("euro truck",)),
    ("Microsoft Flight Simulator", ("flight simulator",)),
    ("iRacing", ("iracing",)),
    ("Assetto Corsa", ("assetto corsa",)),
    ("Geometry Dash", ("geometry dash",)),
    ("Subway Surfers", ("subway surfers",)),
    ("Clash Royale", ("clash royale",)),
    ("Clash of Clans", ("clash of clans",)),
    ("Brawl Stars", ("brawl stars",)),
    ("Mobile Legends", ("mobile legends",)),
    ("Pokemon", ("pokemon",)),
    ("Mario Kart", ("mario kart",)),
    ("Super Smash Bros", ("smash bros", "super smash")),
    ("The Legend of Zelda", ("zelda", "breath of the wild", "tears of the kingdom")),
    ("Splatoon", ("splatoon",)),
    ("Kirby", ("kirby",)),
    ("Sonic the Hedgehog", ("sonic the hedgehog", "sonic")),
    ("Five Nights at Freddy's", ("five nights at freddy", "fnaf")),
    ("Resident Evil", ("resident evil",)),
    ("Silent Hill", ("silent hill",)),
    ("Outlast", ("outlast",)),
    ("Poppy Playtime", ("poppy playtime",)),
    ("Garten of Banban", ("garten of banban",)),
    ("Baldi's Basics", ("baldi's basics", "baldis basics")),
)

_GAMING_CATEGORY_TOKENS = (
    "gaming",
    "video game",
    "esports",
    "let's play",
    "lets play",
)
_GAMING_TAG_TOKENS = (
    "gameplay",
    "gaming",
    "playthrough",
    "walkthrough",
    "speedrun",
    "esports",
    "videojuego",
    "videojuegos",
    "directo",
    "stream",
)
_GAMING_TITLE_TOKENS = (
    "gameplay",
    "playthrough",
    "walkthrough",
    "speedrun",
    "directo",
    "stream",
    "highlights",
    "twitch",
    "partida",
)

_GENERIC_CONTEXT = re.compile(
    r"^(momento|momentos|mejor momento|mejores momentos|clip|clips|short|shorts|"
    r"highlight|highlights|resumen|recopilaci[oó]n|directo|stream|video|"
    r"fragmento|fragmentos|parte|episodio|tiktok)\b",
    re.IGNORECASE,
)
_TRAILING_CONNECTORS = {
    "a",
    "al",
    "and",
    "con",
    "de",
    "del",
    "el",
    "en",
    "for",
    "in",
    "la",
    "las",
    "los",
    "o",
    "of",
    "on",
    "the",
    "to",
    "un",
    "una",
    "with",
    "y",
}


def _ascii(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text or "")
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    return plain.lower()


def _words(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _ascii(text)).strip()


def clean_text(text: Any, limit: int = 200) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(value) > limit:
        value = value[:limit].rsplit(" ", 1)[0].strip()
    return value


def clean_streamer(value: Any) -> str:
    name = clean_text(value, 80)
    name = re.sub(r"\s*[-–—]\s*(topic|vevo|youtube)\s*$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s+(official|oficial)$", "", name, flags=re.IGNORECASE)
    name = name.strip(" -–—|:·@")
    return name[:40].strip()


def detect_game(*texts: Any) -> str:
    corpus = " ".join(_words(str(text or "")) for text in texts if text)
    if not corpus:
        return ""
    corpus = f" {corpus} "
    best_name = ""
    best_score = 0
    for name, aliases in _GAME_LIBRARY:
        score = 0
        for alias in aliases:
            needle = f" {_words(alias)} "
            if needle.strip():
                score += corpus.count(needle)
        if score > best_score:
            best_name = name
            best_score = score
    return best_name


def _looks_gaming(*, title: str, tags: list[str], categories: list[str]) -> bool:
    lowered_title = _words(title)
    if any(token in lowered_title for token in _GAMING_TITLE_TOKENS):
        return True
    lowered_categories = [_words(category) for category in categories]
    if any(
        token in category
        for category in lowered_categories
        for token in _GAMING_CATEGORY_TOKENS
    ):
        return True
    lowered_tags = {_words(tag) for tag in tags}
    return any(token in lowered_tags for token in _GAMING_TAG_TOKENS)


def source_meta_from_info(info: dict[str, Any]) -> dict[str, Any]:
    title = clean_text(info.get("title"), 220)
    description = clean_text(info.get("description"), 1200)
    tags = [clean_text(tag, 60) for tag in (info.get("tags") or []) if tag][:40]
    categories = [
        clean_text(category, 60) for category in (info.get("categories") or []) if category
    ]
    channel = clean_streamer(
        info.get("channel") or info.get("uploader") or info.get("creator") or ""
    )
    game = detect_game(title, description, " ".join(tags), " ".join(categories))
    is_gaming = bool(game) or _looks_gaming(
        title=title, tags=tags, categories=categories
    )
    try:
        duration = float(info.get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0.0
    try:
        width = int(info.get("width") or 0)
    except (TypeError, ValueError):
        width = 0
    try:
        height = int(info.get("height") or 0)
    except (TypeError, ValueError):
        height = 0
    return {
        "source_title": title,
        "title": title,
        "streamer": channel,
        "channel": channel,
        "uploader": clean_text(info.get("uploader"), 80),
        "game": game,
        "is_gaming": is_gaming,
        "description": description,
        "tags": tags[:20],
        "categories": categories,
        "duration": duration,
        "width": width,
        "height": height,
        "fps": float(info.get("fps") or 0) if info.get("fps") else 0.0,
        "upload_date": clean_text(info.get("upload_date"), 20),
        "webpage_url": str(info.get("webpage_url") or ""),
        "thumbnail": str(info.get("thumbnail") or ""),
    }


def source_meta_from_upload(
    *,
    title: str,
    filename: str = "",
    streamer: str = "",
    game: str = "",
) -> dict[str, Any]:
    clean_title = clean_text(title or filename, 220)
    channel = clean_streamer(streamer)
    detected = detect_game(clean_title, filename)
    chosen_game = clean_text(game, 60) or detected
    return {
        "source_title": clean_title,
        "title": clean_title,
        "streamer": channel,
        "channel": channel,
        "game": chosen_game,
        "is_gaming": bool(chosen_game),
        "description": "",
        "tags": [],
        "categories": [],
        "duration": 0.0,
        "width": 0,
        "height": 0,
        "fps": 0.0,
    }


def merge_source_meta(
    base: dict[str, Any] | None, detected: dict[str, Any] | None
) -> dict[str, Any]:
    merged = dict(detected or {})
    for key, value in (base or {}).items():
        if value not in (None, "", [], {}):
            merged[key] = value
    streamer = clean_streamer(merged.get("streamer") or merged.get("channel") or "")
    game = clean_text(merged.get("game"), 60) or detect_game(
        merged.get("title"), merged.get("description")
    )
    merged["streamer"] = streamer
    merged["channel"] = clean_streamer(merged.get("channel") or streamer)
    merged["game"] = game
    merged["is_gaming"] = bool(game) or bool(merged.get("is_gaming"))
    return merged


def enrich_source_meta(meta: dict[str, Any], transcript_text: str) -> dict[str, Any]:
    enriched = dict(meta or {})
    if not enriched.get("game"):
        game = detect_game(transcript_text[:12000])
        if game:
            enriched["game"] = game
            enriched["is_gaming"] = True
    if not enriched.get("streamer"):
        enriched["streamer"] = clean_streamer(
            enriched.get("channel") or enriched.get("uploader") or ""
        )
    if enriched.get("game") and not enriched.get("is_gaming"):
        enriched["is_gaming"] = True
    return enriched


def _strip_tail(text: str) -> str:
    words = text.split()
    while words and _words(words[-1]) in _TRAILING_CONNECTORS:
        words.pop()
    return " ".join(words)


def _context_candidate(text: Any, streamer: str, game: str) -> str:
    candidate = clean_text(text, 160)
    if not candidate or _GENERIC_CONTEXT.match(candidate):
        return ""
    candidate = re.sub(
        r"^(clip|clips|short|shorts|tiktok|video|momento)\s*[:\-|]\s*",
        "",
        candidate,
        flags=re.IGNORECASE,
    )
    candidate = re.sub(r"https?://\S+", "", candidate)
    candidate = re.sub(r"[#@]\S+", "", candidate)
    for value in (streamer, game):
        if value:
            candidate = re.sub(
                rf"\b{re.escape(value)}\b", " ", candidate, flags=re.IGNORECASE
            )
    candidate = re.sub(r"\s+", " ", candidate).strip(" -–—|:·.,;\"'“”")
    if len(candidate) < 4:
        return ""
    words = candidate.split()
    if len(words) > 8:
        candidate = " ".join(words[:8])
    candidate = _strip_tail(candidate).strip(" -–—|:·.,;\"'“”")
    if len(candidate) < 4:
        return ""
    if len(candidate) > 48:
        candidate = candidate[:48].rsplit(" ", 1)[0].strip()
    return candidate.upper()


def build_overlay(
    meta: dict[str, Any] | None,
    clip: dict[str, Any] | None,
    *,
    language: str | None = None,
) -> dict[str, Any]:
    del language  # Context lines stay in the transcript's language.
    source = meta or {}
    item = clip or {}
    streamer = clean_streamer(source.get("streamer") or source.get("channel") or "")
    game = clean_text(source.get("game"), 60)
    context = ""
    for value in (item.get("context"), item.get("title"), item.get("hook")):
        context = _context_candidate(value, streamer, game)
        if context:
            break
    return {
        "kicker": "",
        "context": context[:52].strip(),
        "streamer": streamer,
        "game": game,
        "is_gaming": bool(source.get("is_gaming")) or bool(game),
        "context_seconds": 5.5,
    }
