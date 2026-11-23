from __future__ import annotations

import math
import re
import unicodedata
from bisect import bisect_left, bisect_right
from functools import lru_cache
from typing import Any, Iterable

# The ten editorial buckets requested by the product.  The stored value stays a
# short slug so it is stable in the database and in the API; the UI owns the
# uppercase presentation.
CATEGORY_ORDER = (
    "angry",
    "funny",
    "crazy_reactions",
    "epic",
    "unexpected",
    "scary",
    "fails",
    "wins",
    "drama",
    "shocking",
)

CATEGORY_INFO: dict[str, dict[str, str]] = {
    "angry": {
        "label": "ANGRY MOMENTS",
        "short": "Enfado",
        "hashtag": "#angrymoments",
    },
    "funny": {
        "label": "FUNNY MOMENTS",
        "short": "Humor",
        "hashtag": "#funnymoments",
    },
    "crazy_reactions": {
        "label": "CRAZY REACTIONS",
        "short": "Reacción",
        "hashtag": "#crazyreactions",
    },
    "epic": {
        "label": "EPIC MOMENTS",
        "short": "Épico",
        "hashtag": "#epicmoments",
    },
    "unexpected": {
        "label": "UNEXPECTED MOMENTS",
        "short": "Inesperado",
        "hashtag": "#unexpectedmoments",
    },
    "scary": {
        "label": "SCARY MOMENTS",
        "short": "Miedo",
        "hashtag": "#scarymoments",
    },
    "fails": {
        "label": "FAILS",
        "short": "Fail",
        "hashtag": "#fails",
    },
    "wins": {
        "label": "WINS",
        "short": "Victoria",
        "hashtag": "#wins",
    },
    "drama": {
        "label": "DRAMA",
        "short": "Drama",
        "hashtag": "#drama",
    },
    "shocking": {
        "label": "SHOCKING MOMENTS",
        "short": "Shock",
        "hashtag": "#shockingmoments",
    },
}

# Phrase groups are deliberately bilingual.  The app currently gets Spanish
# and English transcripts most often, and a phrase such as "no puede ser"
# survives ASR much better than a single isolated token.
TEXT_LEXICON: dict[str, tuple[str, ...]] = {
    "anger": (
        "enfad",
        "enfado",
        "rabia",
        "furios",
        "cabread",
        "harto",
        "harto de",
        "me cago",
        "me saca de quicio",
        "no me jodas",
        "gilipollas",
        "imbecil",
        "idiota",
        "estupido",
        "tramposo",
        "cheater",
        "camper",
        "campero",
        "noob",
        "rage",
        "angry",
        "pissed",
        "mad as hell",
        "fuck this",
        "what the fuck",
        "bullshit",
        "stupid",
        "idiot",
    ),
    "humor": (
        "jaja",
        "jajaja",
        "jeje",
        "haha",
        "hahaha",
        "lol",
        "lmao",
        "rofl",
        "risa",
        "gracioso",
        "graciosa",
        "broma",
        "chiste",
        "cringe",
        "meme",
        "funny",
        "joke",
        "laugh",
        "bruh",
        "xd",
        "wtf",
        "no way",
        "que risa",
        "me muero de risa",
    ),
    "surprise": (
        "no puede ser",
        "no me lo puedo creer",
        "no me lo creo",
        "increible",
        "impresionante",
        "que acaba de pasar",
        "que ha pasado",
        "de repente",
        "de la nada",
        "inesperado",
        "sorpresa",
        "shock",
        "locura",
        "insane",
        "crazy",
        "unbelievable",
        "imposible",
        "what just happened",
        "what happened",
        "no way",
        "wow",
        "whoa",
        "madre mia",
        "dios mio",
    ),
    "fear": (
        "miedo",
        "susto",
        "asust",
        "aterrador",
        "terror",
        "horror",
        "no me hagas",
        "detras de ti",
        "detras de mi",
        "cuidado",
        "scary",
        "fear",
        "jumpscare",
        "creepy",
        "amenaza",
        "tension",
        "nervios",
        "estoy temblando",
        "me va a dar algo",
    ),
    "celebration": (
        "vamoooos",
        "yes",
        "lets go",
        "let's go",
        "gg",
        "victoria",
        "gane",
        "ganamos",
        "campeon",
        "celebracion",
        "win",
        "won",
        "victory",
        "clutch",
        "pentakill",
        "lo logre",
        "lo logramos",
        "lo hicimos",
        "lo conseguimos",
        "por fin",
    ),
    "loss": (
        "perdi",
        "perdimos",
        "derrota",
        "fracaso",
        "falle",
        "fallo",
        "fail",
        "error",
        "morir",
        "morí",
        "death",
        "lost",
        "defeat",
        "mistake",
        "me equivoque",
        "arruine",
        "throw",
        "threw",
        "culpa",
        "nooo",
        "se acabo",
        "se termino",
    ),
    "conflict": (
        "pelea",
        "discusion",
        "problema",
        "conflicto",
        "mentira",
        "traicion",
        "traiciono",
        "insulto",
        "report",
        "ban",
        "toxic",
        "argument",
        "fight",
        "drama",
        "beef",
        "contra",
        "equipo",
        "team",
        "compañero",
        "companero",
        "chat",
        "no estoy de acuerdo",
        "estas equivocado",
    ),
    "epic": (
        "jugada",
        "jugadon",
        "impresionante",
        "epico",
        "epic",
        "insane",
        "best play",
        "highlight",
        "perfect",
        "no scope",
        "noscope",
        "360",
        "pentakill",
        "ace",
        "record",
        "clutch",
        "brutal",
        "monstruoso",
        "una locura",
    ),
    "shock": (
        "increible",
        "shocking",
        "brutal",
        "salvaje",
        "enfermo",
        "wtf",
        "what the fuck",
        "locura",
        "unbelievable",
        "surreal",
        "trauma",
        "perturbador",
        "no puede ser",
        "que cojones",
        "que mierda",
        "horrible",
    ),
    "exaggeration": (
        "demasiado",
        "exagerado",
        "literalmente",
        "en serio",
        "no way",
        "bro",
        "dude",
        "hermano",
        "tio",
        "holy",
        "jesus",
        "dios",
        "por dios",
        "increible",
        "brutal",
    ),
    "chat": (
        "chat",
        "comentario",
        "donacion",
        "donation",
        "sub",
        "mensaje",
        "twitch",
        "viewers",
        "espectadores",
        "mira el chat",
        "leed el chat",
    ),
    "game": (
        "partida",
        "juego",
        "game",
        "kill",
        "elimine",
        "gane",
        "perdi",
        "nivel",
        "boss",
        "jefe",
        "ronda",
        "round",
        "match",
        "lobby",
        "server",
        "equipo",
        "team",
        "respawn",
        "revive",
        "revivir",
        "zona",
        "torre",
        "base",
    ),
}

LAUGH_RE = re.compile(r"(?:ja){2,}|(?:ha){2,}|jeje+|jiji+|\blol\b|\blmao\b|\brofl\b", re.I)
INSULT_RE = re.compile(
    r"\b(?:idiota|imbecil|estupido|gilipollas|puta|mierda|joder|coño|fuck|shit|"
    r"bastard|asshole|bitch|retard)\b",
    re.I,
)


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text or "")
    ascii_text = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", ascii_text.lower()).strip()


@lru_cache(maxsize=512)
def _phrase_pattern(phrase: str) -> re.Pattern[str]:
    # A plain substring search turns "si" into a celebration on every
    # "siempre" and "sistema". Word boundaries keep short tokens exact.
    normalized = normalize(phrase)
    return re.compile(rf"(?<![a-z0-9]){re.escape(normalized)}(?![a-z0-9])")


@lru_cache(maxsize=1)
def _phrases_by_first_token() -> dict[str, list[tuple[str, re.Pattern, float]]]:
    by_token = {}
    for group, phrases in TEXT_LEXICON.items():
        for phrase in phrases:
            first = re.search(r"[a-z0-9]+", normalize(phrase)).group()
            weight = 1.0 + min(0.6, 0.08 * max(0, len(phrase.split()) - 1))
            by_token.setdefault(first, []).append((group, _phrase_pattern(phrase), weight))
    return by_token


def _scaled(value: float, *, cap: float = 1.0) -> float:
    return max(0.0, min(cap, value))


def text_affect(text: str) -> dict[str, float]:
    """Return cheap, explainable emotional signals for a transcript span.

    The values are 0..1 so the caller can combine them with audio and visual
    probabilities without pretending they are calibrated percentages.
    """
    source = text or ""
    normalized = normalize(source)
    tokens = re.findall(r"[a-z0-9]+", normalized)
    token_count = max(1, len(tokens))
    exclamations = source.count("!") + source.count("¡")
    questions = source.count("?") + source.count("¿")
    caps = sum(1 for char in source if char.isupper())
    letters = max(1, sum(1 for char in source if char.isalpha()))
    caps_ratio = caps / letters
    laughter = 1.0 if LAUGH_RE.search(source) else 0.0
    insults = len(INSULT_RE.findall(source))

    hits = dict.fromkeys(TEXT_LEXICON, 0.0)
    by_token = _phrases_by_first_token()
    for token in set(tokens):
        for group, pattern, weight in by_token.get(token, ()):
            if pattern.search(normalized):
                hits[group] += weight
    dimensions = {group: _scaled(0.28 * value) for group, value in hits.items()}

    # Punctuation and delivery are independent from vocabulary.  A long,
    # complete sentence with one exclamation is milder than five short bursts.
    delivery = _scaled(exclamations * 0.16 + questions * 0.05)
    dimensions["exclamations"] = float(exclamations)
    dimensions["questions"] = float(questions)
    dimensions["laughter"] = laughter
    dimensions["insults"] = float(insults)
    dimensions["caps"] = _scaled(caps_ratio * 1.8)
    dimensions["delivery"] = delivery
    dimensions["shouting"] = _scaled(
        0.58 * delivery + 0.22 * dimensions["exaggeration"] + 0.20 * dimensions["anger"]
    )
    dimensions["word_count"] = float(token_count)
    dimensions["unique_ratio"] = (
        len(set(tokens)) / float(token_count) if tokens else 0.0
    )
    return dimensions


def text_dimensions(affect: dict[str, float]) -> dict[str, float]:
    """Map raw lexical groups to the editorial scoring dimensions."""
    anger = affect.get("anger", 0.0)
    humor = affect.get("humor", 0.0)
    surprise = affect.get("surprise", 0.0)
    fear = affect.get("fear", 0.0)
    celebration = affect.get("celebration", 0.0)
    loss = affect.get("loss", 0.0)
    conflict = affect.get("conflict", 0.0)
    epic = affect.get("epic", 0.0)
    shock = affect.get("shock", 0.0)
    exaggeration = affect.get("exaggeration", 0.0)
    shouting = affect.get("shouting", 0.0)
    laughter = affect.get("laughter", 0.0)
    delivery = affect.get("delivery", 0.0)

    intensity = _scaled(
        0.32 * shouting
        + 0.22 * anger
        + 0.18 * surprise
        + 0.14 * celebration
        + 0.08 * fear
        + 0.06 * laughter
    )
    surprise_score = _scaled(
        0.52 * surprise + 0.22 * shock + 0.14 * delivery + 0.12 * fear
    )
    humor_score = _scaled(
        0.68 * humor + 0.22 * laughter + 0.10 * exaggeration * (1.0 - anger)
    )
    originality = _scaled(
        0.24 * shock
        + 0.20 * surprise
        + 0.16 * epic
        + 0.12 * humor
        + 0.10 * fear
        + 0.10 * affect.get("unique_ratio", 0.0)
    )
    importance = _scaled(
        0.28 * max(epic, celebration)
        + 0.24 * max(loss, conflict)
        + 0.20 * shock
        + 0.16 * anger
        + 0.12 * affect.get("game", 0.0)
    )
    conversation = _scaled(
        0.30 * affect.get("questions", 0.0) / 3.0
        + 0.24 * conflict
        + 0.18 * affect.get("chat", 0.0)
        + 0.14 * affect.get("word_count", 0.0) / 35.0
        + 0.14 * affect.get("unique_ratio", 0.0)
    )
    entertainment = _scaled(
        0.30 * intensity
        + 0.26 * humor_score
        + 0.22 * surprise_score
        + 0.12 * importance
        + 0.10 * max(epic, celebration)
    )
    hook = _scaled(
        0.30 * intensity
        + 0.22 * humor_score
        + 0.20 * surprise_score
        + 0.16 * max(shock, epic)
        + 0.12 * delivery
    )
    return {
        "intensity": intensity,
        "surprise": surprise_score,
        "humor": humor_score,
        "originality": originality,
        "importance": importance,
        "conversation": conversation,
        "entertainment": entertainment,
        "hook": hook,
        "retention": _scaled(
            0.34 * importance + 0.28 * max(celebration, loss) + 0.20 * conflict + 0.18 * absorption(affect)
        ),
        "context": _scaled(
            0.32 * absorption(affect) + 0.24 * conflict + 0.22 * affect.get("word_count", 0.0) / 30.0
        ),
        "anger": anger,
        "humor_raw": humor,
        "surprise_raw": surprise,
        "fear": fear,
        "celebration": celebration,
        "loss": loss,
        "conflict": conflict,
        "epic": epic,
        "shock": shock,
    }


def absorption(affect: dict[str, float]) -> float:
    """How much narrative material a span has for a standalone clip."""
    words = affect.get("word_count", 0.0)
    unique = affect.get("unique_ratio", 0.0)
    return _scaled(min(1.0, words / 28.0) * 0.65 + unique * 0.35)


def _reducer(values: list[float], mode: str) -> float:
    if not values:
        return 0.0
    if mode == "mean":
        return sum(values) / len(values)
    if mode == "sum":
        return sum(values)
    return max(values)


def timeline_summary(
    timeline: dict[str, Any] | None,
    start: float,
    end: float,
    keys: Iterable[str],
    *,
    reducer: str = "max",
) -> dict[str, float]:
    """Read a compact window summary from a sampled timeline.

    Timelines are produced by the audio and visual analyzers and contain a
    sorted ``times`` list plus one list per feature.  They stay in memory only
    for the duration of the job.
    """
    if not timeline:
        return {key: 0.0 for key in keys}
    times = timeline.get("times") or []
    if not times:
        return {key: 0.0 for key in keys}
    low = max(0, bisect_left(times, start))
    high = min(len(times), bisect_right(times, end))
    result: dict[str, float] = {}
    for key in keys:
        values = timeline.get(key) or []
        selected = [
            float(values[index])
            for index in range(low, high)
            if index < len(values) and values[index] is not None
        ]
        result[key] = _reducer(selected, reducer)
    return result


def events_in_window(
    events: list[dict[str, Any]] | None,
    start: float,
    end: float,
    *,
    pad: float = 0.0,
) -> list[dict[str, Any]]:
    if not events:
        return []
    return [
        event
        for event in events
        if float(event.get("end", 0.0)) >= start - pad
        and float(event.get("start", 0.0)) <= end + pad
    ]


def _event_strength(events: Iterable[dict[str, Any]]) -> float:
    best = 0.0
    for event in events:
        best = max(best, float(event.get("score", 0.0)))
    return best


def summarize_audio(
    audio: dict[str, Any] | None,
    start: float,
    end: float,
) -> dict[str, Any]:
    if not audio:
        return {
            "available": False,
            "intensity": 0.0,
            "peak_delta": 0.0,
            "mean_delta": 0.0,
            "events": [],
            "event_strength": 0.0,
            "laughter": False,
            "scream": False,
            "silence": False,
        }
    base = float(audio.get("baseline_db") or -60.0)
    values = timeline_summary(
        audio,
        start,
        end,
        ("rms_db", "centroid", "zcr", "flux", "high_ratio"),
        reducer="max",
    )
    mean = timeline_summary(audio, start, end, ("rms_db",), reducer="mean")
    events = events_in_window(audio.get("events"), start, end, pad=0.4)
    peak_delta = values["rms_db"] - base
    mean_delta = mean["rms_db"] - base
    event_strength = _event_strength(events)
    kind_set = {str(event.get("kind")) for event in events}
    intensity = _scaled(
        (50.0 + peak_delta * 3.6) / 100.0
        + 0.20 * event_strength / 100.0
        + 0.08 * values["flux"]
    )
    return {
        "available": True,
        "intensity": intensity * 100.0,
        "peak_delta": peak_delta,
        "mean_delta": mean_delta,
        "peak_db": values["rms_db"],
        "centroid": values["centroid"],
        "zcr": values["zcr"],
        "flux": values["flux"],
        "high_ratio": values["high_ratio"],
        "events": events,
        "event_strength": event_strength,
        "laughter": "laughter" in kind_set,
        "scream": "scream" in kind_set,
        "silence": "sudden_silence" in kind_set,
    }


def summarize_visual(
    visual: dict[str, Any] | None,
    start: float,
    end: float,
) -> dict[str, Any]:
    if not visual:
        return {
            "available": False,
            "intensity": 0.0,
            "motion": 0.0,
            "face_motion": 0.0,
            "head_motion": 0.0,
            "face_crop_motion": 0.0,
            "mouth_motion": 0.0,
            "face_present": 0.0,
            "events": [],
            "event_strength": 0.0,
            "scene_cuts": 0.0,
            "reaction": False,
        }
    values = timeline_summary(
        visual,
        start,
        end,
        (
            "motion",
            "center_motion",
            "face_motion",
            "head_motion",
            "face_crop_motion",
            "mouth_motion",
            "face_present",
            "hist_diff",
        ),
        reducer="max",
    )
    events = events_in_window(visual.get("events"), start, end, pad=0.4)
    # A cut is a structural signal, not a reaction. Let it count as a scene
    # cut without turning every edit into a high-intensity emotional moment.
    reaction_events = [
        event
        for event in events
        if str(event.get("kind") or "") not in {"scene_cut", "scene_change"}
    ]
    event_strength = _event_strength(reaction_events)
    motion_median = float(visual.get("motion_median") or 0.0)
    motion_mad = float(visual.get("motion_mad") or 0.01)
    relative = max(0.0, values["motion"] - motion_median) / max(0.008, motion_mad)
    if reaction_events:
        intensity = _scaled(0.42 + 0.18 * relative + 0.40 * event_strength / 100.0)
    else:
        # Raw camera/talking motion without a face, mouth or motion event is
        # context, not an emotional reaction. Keep it from inflating scores.
        intensity = _scaled(0.18 + 0.10 * relative)
    kind_set = {str(event.get("kind")) for event in events}
    return {
        "available": True,
        "intensity": intensity * 100.0,
        "motion": values["motion"],
        "center_motion": values["center_motion"],
        "face_motion": values["face_motion"],
        "head_motion": values["head_motion"],
        "face_crop_motion": values["face_crop_motion"],
        "mouth_motion": values["mouth_motion"],
        "face_present": values["face_present"],
        "hist_diff": values["hist_diff"],
        "events": events,
        "event_strength": event_strength,
        "scene_cuts": float(len(kind_set & {"scene_cut", "scene_change"})),
        "reaction": bool(kind_set & {"face_reaction", "face_expression", "visual_reaction"}),
    }


def _category_scores(
    text: dict[str, float],
    audio: dict[str, Any],
    visual: dict[str, Any],
) -> dict[str, float]:
    intensity = max(text.get("intensity", 0.0), audio.get("intensity", 0.0) / 100.0, visual.get("intensity", 0.0) / 100.0)
    surprise = max(text.get("surprise", 0.0), visual.get("event_strength", 0.0) / 100.0 * 0.7)
    humor = max(text.get("humor", 0.0), 0.58 if audio.get("laughter") else 0.0)
    fear = text.get("fear", 0.0)
    celebration = text.get("celebration", 0.0)
    loss = text.get("loss", 0.0)
    conflict = text.get("conflict", 0.0)
    epic = text.get("epic", 0.0)
    shock = text.get("shock", 0.0)
    anger = text.get("anger", 0.0)
    audio_intensity = audio.get("intensity", 0.0) / 100.0
    visual_intensity = visual.get("intensity", 0.0) / 100.0
    scene_cuts = min(1.0, visual.get("scene_cuts", 0.0) / 2.0)
    reaction = 1.0 if visual.get("reaction") else 0.0
    scream = 1.0 if audio.get("scream") else 0.0

    scores = {
        "angry": 100.0
        * _scaled(
            0.54 * anger
            + 0.18 * conflict
            + 0.12 * intensity
            + 0.10 * scream
            + 0.06 * audio_intensity
            - 0.30 * celebration
        ),
        "funny": 100.0
        * _scaled(0.60 * humor + 0.16 * intensity + 0.14 * surprise + 0.10 * reaction),
        "crazy_reactions": 100.0
        * _scaled(
            0.36 * intensity
            + 0.24 * surprise
            + 0.18 * text.get("shouting", 0.0)
            + 0.12 * reaction
            + 0.10 * visual_intensity
        ),
        "epic": 100.0
        * _scaled(
            0.46 * epic
            + 0.24 * celebration
            + 0.16 * visual_intensity
            + 0.08 * scene_cuts
            + 0.06 * intensity
        ),
        "unexpected": 100.0
        * _scaled(
            0.46 * surprise
            + 0.20 * shock
            + 0.16 * scene_cuts
            + 0.10 * reaction
            + 0.08 * intensity
        ),
        "scary": 100.0
        * _scaled(
            0.62 * fear
            + 0.18 * surprise
            + 0.12 * scream
            + 0.08 * visual_intensity
        ),
        "fails": 100.0
        * _scaled(
            0.48 * loss
            + 0.20 * conflict
            + 0.14 * humor
            + 0.10 * intensity
            + 0.08 * visual_intensity
        ),
        "wins": 100.0
        * _scaled(
            0.50 * celebration
            + 0.26 * epic
            + 0.12 * intensity
            + 0.06 * visual_intensity
            + 0.06 * audio_intensity
        ),
        "drama": 100.0
        * _scaled(
            0.54 * conflict
            + 0.20 * anger
            + 0.12 * intensity
            + 0.08 * text.get("conversation", 0.0)
            + 0.06 * surprise
        ),
        "shocking": 100.0
        * _scaled(
            0.44 * shock
            + 0.24 * surprise
            + 0.16 * intensity
            + 0.10 * fear
            + 0.06 * visual_intensity
        ),
    }
    # Audio and visual evidence should not manufacture a "funny" label on its
    # own.  A laugh exists only when the transcript or the laugh detector says
    # so; a loud shout without a category remains "crazy reactions" instead of
    # being forced into anger.
    if not text.get("humor_raw") and not audio.get("laughter"):
        scores["funny"] *= 0.72
    if not text.get("anger") and not text.get("conflict"):
        scores["angry"] *= 0.70
    return {key: round(_scaled(value / 100.0) * 100.0, 1) for key, value in scores.items()}


def choose_category(
    text: dict[str, float],
    audio: dict[str, Any] | None = None,
    visual: dict[str, Any] | None = None,
) -> tuple[str, dict[str, float]]:
    scores = _category_scores(text, audio or {}, visual or {})
    best_key = "unexpected"
    best_score = -1.0
    for key in CATEGORY_ORDER:
        value = scores.get(key, 0.0)
        if value > best_score + 0.01:
            best_key = key
            best_score = value
    # A scream plus a face reaction is the generic "crazy reaction" bucket, but
    # it should not erase a specific emotion that scored almost as high.  A
    # funny laugh, an angry rant and a scared shout all deserve their own shelf.
    if best_key == "crazy_reactions":
        specific = {
            key: scores.get(key, 0.0)
            for key in (
                "angry",
                "funny",
                "scary",
                "wins",
                "epic",
                "fails",
                "drama",
                "shocking",
            )
        }
        near_key = max(specific, key=specific.get)
        if specific[near_key] >= best_score - 8.0:
            best_key = near_key
            best_score = specific[near_key]
    # A completely flat span is not a category claim.  Keep it in the generic
    # bucket that describes the least specific interesting event.
    if best_score < 18.0:
        best_key = "unexpected"
    return best_key, scores


def category_label(category: str) -> str:
    return CATEGORY_INFO.get(category, {}).get("label", "UNEXPECTED MOMENTS")


def category_short(category: str) -> str:
    return CATEGORY_INFO.get(category, {}).get("short", "Momento")


def category_hashtag(category: str) -> str:
    return CATEGORY_INFO.get(category, {}).get("hashtag", "#shorts")


def category_signals(
    category: str,
    text: dict[str, float],
    audio: dict[str, Any],
    visual: dict[str, Any],
) -> list[str]:
    tags: list[str] = []
    if category in CATEGORY_INFO:
        tags.append(CATEGORY_INFO[category]["short"])
    if audio.get("scream"):
        tags.append("Grito")
    if audio.get("laughter"):
        tags.append("Risa")
    if audio.get("event_strength", 0.0) >= 55:
        tags.append("Pico de audio")
    if visual.get("reaction"):
        tags.append("Reacción facial")
    if visual.get("scene_cuts", 0.0) >= 1:
        tags.append("Cambio de escena")
    if text.get("surprise", 0.0) >= 0.35:
        tags.append("Sorpresa")
    if text.get("humor", 0.0) >= 0.35:
        tags.append("Humor")
    if text.get("conflict", 0.0) >= 0.35:
        tags.append("Conflicto")
    if text.get("celebration", 0.0) >= 0.35:
        tags.append("Celebración")
    return tags[:4]


def event_clusters(
    events: Iterable[dict[str, Any]],
    *,
    gap: float = 3.5,
) -> list[list[dict[str, Any]]]:
    ordered = sorted(
        (dict(event) for event in events),
        key=lambda item: float(item.get("start", 0.0)),
    )
    clusters: list[list[dict[str, Any]]] = []
    for event in ordered:
        if not clusters:
            clusters.append([event])
            continue
        previous = clusters[-1]
        last_end = max(float(item.get("end", 0.0)) for item in previous)
        if float(event.get("start", 0.0)) <= last_end + gap:
            previous.append(event)
        else:
            clusters.append([event])
    return clusters
