"""Editorial decisions based on the selected passage and the creator's own feedback."""

from __future__ import annotations

import re
from collections import Counter
from statistics import median

from .editorial import evidence_sentences, normalize, story_penalty, tokens

FACTOR_TIPS = {
    "hook": "Prueba un rótulo que adelante la pregunta central.",
    "clarity": "Comprueba si el primer subtítulo presenta a quien habla y el tema.",
    "pacing": "Revisa las pausas entre la preparación y el remate.",
    "retention": "Termina después de la respuesta o reacción que resuelve la apertura.",
    "surprise": "Prueba una apertura que contraste la expectativa con el resultado.",
    "entertainment": "Conserva la reacción que da sentido al momento.",
    "intensity": "Deja respirar la reacción antes del corte final.",
}
LABELS = dict(
    hook="gancho",
    clarity="claridad",
    pacing="ritmo",
    retention="cierre",
    surprise="sorpresa",
    entertainment="entretenimiento",
    intensity="intensidad",
)


def transcript(clip):
    return " ".join(
        c.get("text", "") for c in (clip.get("subtitles") or {}).get("cues", [])
    ).strip()


def hook_options(clip, offset=0, profile=None):
    text = transcript(clip)
    sentences = [s for s in evidence_sentences(text) if len(s) <= 120]
    if not sentences:
        sentences = [
            s
            for s in re.split(r"(?<=[.!?…])\s+", text)
            if 2 <= len(s.split()) and len(s) <= 120
        ]
    sentences = list(dict.fromkeys(sentences))
    title_words = tokens(clip.get("title") or "")
    learned_topics = tokens(" ".join((profile or {}).get("topics", {})))
    ranked = sorted(
        sentences,
        key=lambda s: (
            len(learned_topics & tokens(s)),
            len(title_words & tokens(s)),
            -story_penalty([s]),
        ),
        reverse=True,
    )
    if ranked:
        offset %= len(ranked)
        ranked = ranked[offset:] + ranked[:offset]
    result = []
    for line in ranked[:5]:
        kind = (
            "Pregunta"
            if line.endswith("?")
            else "Reacción" if line.endswith("!") else "Cita del clip"
        )
        result.append({"kind": kind, "text": line})
    title = (clip.get("title") or "").strip()
    if title and len(title) <= 120 and title not in sentences:
        result.append({"kind": "Título editorial", "text": title})
    return result


def assessment(clip):
    factors = clip.get("score_breakdown") or {}
    available = [
        key for key in FACTOR_TIPS if isinstance(factors.get(key), (int, float))
    ]
    weakest = min(available, key=factors.get) if available else None
    strongest = max(available, key=factors.get) if available else None
    return {
        "strength": (
            f"Destaca por {LABELS[strongest]} ({factors[strongest]}/100)."
            if strongest
            else clip.get("reason") or ""
        ),
        "tip": FACTOR_TIPS.get(weakest, ""),
        "confidence": factors.get("category_confidence"),
    }


def preference_profile(choices):
    styles = Counter(c["style"] for c in choices if c.get("style"))
    categories = Counter(c["category"] for c in choices if c.get("category"))
    durations = [c["end"] - c["start"] for c in choices if c["end"] > c["start"]]
    topics = Counter(t for c in choices for t in set(c.get("tags") or []))
    return {
        "examples": len(choices),
        "style": styles.most_common(1)[0][0] if styles else None,
        "categories": dict(categories.most_common(5)),
        "topics": dict(topics.most_common(8)),
        "duration": round(median(durations), 1) if durations else None,
    }


def preference_bonus(candidate, profile):
    if not profile or not (profile.get("examples") or profile.get("engagement")):
        return 0.0
    categories = profile.get("categories", {})
    count = categories.get(candidate.get("category"), 0)
    share = count / max(1, sum(categories.values()))
    duration = candidate["end"] - candidate["start"]
    target = profile.get("duration")
    proximity = max(0, 1 - abs(duration - target) / max(1, target)) if target else 0
    topic_overlap = tokens(candidate.get("text") or "") & {
        normalize(t) for t in profile.get("topics", {})
    }
    observed = profile.get("engagement", {}).get(candidate.get("category"), 0)
    return (
        4 * share + 2 * proximity + min(2, len(topic_overlap)) + min(2, 20 * observed)
    )


def week_order(clips, profile):
    pool = [c for c in clips if c.get("status") == "ready" and c.get("video_file")]
    selected = []
    represented = Counter()
    while pool and len(selected) < 7:

        def rank(c):
            return (
                (c.get("score") or 0)
                + preference_bonus(c, profile)
                - 5 * represented[c.get("category")],
                -c["idx"],
            )

        best = max(pool, key=rank)
        group = (best["start"], best["end"])
        pool = [c for c in pool if (c["start"], c["end"]) != group]
        represented[best.get("category")] += 1
        selected.append(best)
    return selected
