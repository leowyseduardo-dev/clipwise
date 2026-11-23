from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from typing import Any, Iterable

_MAX_TITLE = 72

# Function words and discourse markers. Keeping these out of the phrase
# extractor is what stops a title from being the opening "bueno, pues..." line.
_STOPWORDS = frozenset(
    """
    a al algo algun alguna algunos algunas ante antes aquel aquella aquellos aquellas
    aqui asi aun aunque como con contra cual cuales cuando de del desde donde dos
    el ella ellas ellos en entre era eran es esa esas ese eso esos esta estaba estan
    estas este esto estos fue fueron ha habia han hasta hay la las le les lo los mas
    me mi mis mucho mucha muchos muchas muy nada ni no nos nosotros o os otra otras
    otro otros para pero poco poca pocos pocas por porque que quien quienes se sea
    segun ser si sin sobre son su sus tambien tan tanto te tiene tienen todo toda
    todos todas tu tus un una unas uno unos y ya yo
    about above after again against all also am an and any are as at be because been
    before being below between both but by can could did do does doing down during
    each few for from further had has have having he her here hers herself him
    himself his how i if in into is it its itself just me more most my myself no nor
    not now of off on once only or other our ours ourselves out over own same she
    should so some such than that the their theirs them themselves then there these
    they this those through to too under until up very was we were what when where
    which while who whom why will with would you your yours yourself yourselves
    """.split()
)

_FILLERS = frozenset(
    """
    eh em um uh mmm hmm bueno pues vale okay ok este digamos basicamente literally
    like so well and y pero but mira escucha oye look listen
    """.split()
)

# These can sit inside a noun phrase ("secreto del dinero") but are not
# content words on their own.
_SOFT = frozenset(
    """
    a al con de del en entre para por sobre sin que y o
    about and for in of on or that to with
    """.split()
)

# Generic words that make a title sound empty even when the phrase is long.
_BANAL = frozenset(
    """
    esto eso esta este estas estos cosa cosas algo nada todo toda todos todas gente
    persona personas video videos clip clips momento momentos parte partes lugar
    tiempo dia hoy aqui asi bien mal mucho mucha muchos muchas poco poca pocos pocas
    mas menos muy tan mismo misma mismos mismas
    thing things something anything nothing everything people person video clip
    moment part place time day today here really very much many more less same way
    stuff
    """.split()
)

_VERBS = frozenset(
    """
    es son era eran fue fueron ser estar esta estan estaba tener tiene tienen hace
    hacen hacer comete cometen cometer empieza empiezan empezar funciona funcionan
    funcionar cambiar cambia cambian cambio logra logran lograr quiere quieren querer
    puede pueden poder sabe saben saber piensa piensan pensar dice dicen decir cuenta
    cuentan contar ensena ensenan ensenar habla hablan hablar mira miran mirar vamos
    va van ir fui hay
    is are was were be been has have had do does did make makes made get gets got go
    goes went change changes changed work works worked say says said tell tells told
    know knows knew think thinks thought want wants wanted need needs needed can
    could will would should function functions happen happens
    """.split()
)

_QUESTION_WORDS = frozenset(
    """
    que como por que porque cuando donde quien quienes cual cuales cuanto cuanta
    cuantos cuantas what why how when where who whom which whose
    """.split()
)

_CONNECTORS = frozenset(
    """
    y pero porque entonces aunque and but because so then or o
    """.split()
)

_ES_HINTS = frozenset(
    """
    el la los las que de del en por para con no se su lo como pero esto esta nadie
    tienes porque cuando muy mas ya hay es son una un
    """.split()
)
_EN_HINTS = frozenset(
    """
    the and to of in is that you it for on with this what why how was are be have
    has not but they we he she my your from at as so
    """.split()
)

_CATEGORY_TERMS: dict[str, tuple[str, ...]] = {
    "curiosidad": (
        "secreto",
        "nadie",
        "por que",
        "porque",
        "como",
        "verdad",
        "nunca",
        "increible",
        "secret",
        "nobody",
        "why",
        "how",
        "truth",
        "never",
        "amazing",
    ),
    "consejo": (
        "consejo",
        "truco",
        "deberias",
        "tienes que",
        "error",
        "evita",
        "tip",
        "advice",
        "should",
        "mistake",
        "avoid",
        "trick",
    ),
    "dinero": (
        "dinero",
        "dolares",
        "euros",
        "precio",
        "coste",
        "gratis",
        "sueldo",
        "ingresos",
        "money",
        "dollars",
        "price",
        "salary",
        "income",
    ),
    "historia": (
        "historia",
        "cuando",
        "un dia",
        "al final",
        "resulta",
        "story",
        "when",
        "one day",
        "in the end",
        "turns out",
    ),
    "conflicto": (
        "problema",
        "pelea",
        "discusion",
        "contra",
        "fracaso",
        "conflicto",
        "problem",
        "fight",
        "argument",
        "failed",
        "versus",
    ),
    "datos": (
        "dato",
        "cifra",
        "por ciento",
        "estudio",
        "investigacion",
        "percent",
        "study",
        "research",
        "statistics",
    ),
    "emocion": (
        "increible",
        "brutal",
        "loco",
        "terrible",
        "amor",
        "miedo",
        "insane",
        "crazy",
        "love",
        "fear",
        "amazing",
    ),
    "humor": (
        "jaja",
        "risa",
        "gracioso",
        "broma",
        "funny",
        "joke",
        "laugh",
        "lol",
        "haha",
    ),
}

_PUNCH = frozenset(
    """
    secreto nadie error verdad problema resultado conclusion truco consejo cambia
    cambio cambió todo nunca siempre por que como
    secret nobody mistake truth problem result conclusion trick advice changes
    changed everything never always why how
    """.split()
)

_PATTERNS: dict[str, dict[str, tuple[str, ...]]] = {
    "es": {
        "curiosidad": (
            "{topic}: lo que nadie te cuenta",
            "{topic}: el secreto que nadie te dice",
        ),
        "consejo": (
            "{topic}: el consejo que sí funciona",
            "{topic}: el error que casi todos cometen",
        ),
        "dinero": (
            "{topic}: lo que nadie te cuenta sobre el dinero",
            "{topic}: el error que te cuesta dinero",
        ),
        "historia": (
            "{topic}: la historia que cambió todo",
            "{topic}: el momento que lo cambió todo",
        ),
        "conflicto": (
            "{topic}: el problema que nadie quiere ver",
            "{topic}: la verdad del conflicto",
        ),
        "datos": (
            "{topic}: el dato que lo explica todo",
            "{topic}: lo que dicen los números",
        ),
        "emocion": (
            "{topic}: la reacción que nadie esperaba",
            "{topic}: el momento que lo cambió todo",
        ),
        "humor": (
            "{topic}: el momento más divertido",
            "{topic}: la reacción que nadie vio venir",
        ),
        "generic": (
            "{topic}: lo que tienes que saber",
            "{topic}: la clave que nadie te cuenta",
        ),
    },
    "en": {
        "curiosidad": (
            "{topic}: what nobody tells you",
            "{topic}: the secret nobody mentions",
        ),
        "consejo": (
            "{topic}: the advice that actually works",
            "{topic}: the mistake almost everyone makes",
        ),
        "dinero": (
            "{topic}: what nobody tells you about money",
            "{topic}: the mistake that costs you money",
        ),
        "historia": (
            "{topic}: the story that changed everything",
            "{topic}: the moment that changed it all",
        ),
        "conflicto": (
            "{topic}: the problem nobody wants to see",
            "{topic}: the truth behind the conflict",
        ),
        "datos": (
            "{topic}: the detail that explains it all",
            "{topic}: what the numbers say",
        ),
        "emocion": (
            "{topic}: the reaction nobody expected",
            "{topic}: the moment that changed everything",
        ),
        "humor": (
            "{topic}: the funniest moment",
            "{topic}: the reaction nobody saw coming",
        ),
        "generic": (
            "{topic}: what you need to know",
            "{topic}: the detail that changes everything",
        ),
    },
}


def _norm(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text or "")
    ascii_text = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", ascii_text.lower()).strip()


def _tokens(text: str) -> list[str]:
    return re.findall(
        r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9]+(?:['’][A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+)?",
        text or "",
    )


def _token_norm(token: str) -> str:
    return _norm(token).strip(".,!?¿¡…;:\"'()[]{} ")


def _sentence_texts(window_sentences: Iterable[Any]) -> list[str]:
    texts: list[str] = []
    for item in window_sentences:
        text = item if isinstance(item, str) else (item or {}).get("text", "")
        text = re.sub(r"\s+", " ", str(text or "")).strip()
        if text:
            texts.append(text)
    return texts


def _is_content(token: str) -> bool:
    norm = _token_norm(token)
    if not norm or len(norm) < 2:
        return False
    if norm in _STOPWORDS or norm in _FILLERS or norm in _SOFT:
        return False
    if norm in _BANAL or norm in _VERBS or norm in _QUESTION_WORDS:
        return False
    return True


def _content_tokens(text: str) -> list[str]:
    return [norm for norm in (_token_norm(token) for token in _tokens(text)) if norm and _is_content(norm)]


def _language(language: str | None, text: str) -> str:
    code = _norm(language or "").split("-")[0].split("_")[0]
    if code in {"es", "en"}:
        return code
    words = [_token_norm(token) for token in _tokens(text)]
    es_hits = sum(1 for word in words if word in _ES_HINTS)
    en_hits = sum(1 for word in words if word in _EN_HINTS)
    if es_hits > en_hits:
        return "es"
    if en_hits > es_hits:
        return "en"
    if re.search(r"[áéíóúüñ¿¡]", text.lower()):
        return "es"
    return "en"


def _category_hits(text: str) -> list[str]:
    normalized = _norm(text)
    hits: list[str] = []
    for key, terms in _CATEGORY_TERMS.items():
        if any(term in normalized for term in terms):
            hits.append(key)
    return hits


def _clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    text = re.sub(r"^[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9¿¡]+", "", text)
    text = re.sub(r"[,;:·|]+$", "", text).strip()
    return text.strip()


def _strip_tail(text: str) -> str:
    words = text.split()
    while words and _token_norm(words[-1]) in _CONNECTORS | _FILLERS:
        words.pop()
    return " ".join(words)


def _capitalize(text: str) -> str:
    if not text:
        return text
    if text[0] in "¿¡" and len(text) > 1:
        return text[0] + text[1].upper() + text[2:]
    return text[0].upper() + text[1:]


def _fix_question_accents(text: str) -> str:
    replacements = {
        "por que": "por qué",
        "que": "qué",
        "como": "cómo",
        "donde": "dónde",
        "quien": "quién",
        "cuando": "cuándo",
        "cuanto": "cuánto",
        "cual": "cuál",
    }
    match = re.match(r"^(por que|que|como|donde|quien|cuando|cuanto|cual)\b", text, flags=re.IGNORECASE)
    if not match:
        return text
    original = match.group(1)
    replacement = replacements.get(_norm(original), original)
    return replacement + text[len(original):]


def _question(text: str, language: str) -> str:
    text = _strip_tail(_clean_text(text)).strip(" .,;:-")
    if not text:
        return ""
    if language == "es":
        text = text.lstrip("¿?¡! ").rstrip("?¿ ")
        if not text:
            return ""
        text = _fix_question_accents(text)
        return _capitalize(f"¿{text}?")
    text = text.lstrip("?¡! ").rstrip("?")
    return _capitalize(f"{text}?")


_SPECIAL_REWRITES: dict[str, tuple[tuple[str, str], ...]] = {
    "es": (
        (
            r"^la mayoria(?: de la gente)? (?:comete|hace|tiene) el (?:mismo|gran) error(?: cuando| al)? (.+)$",
            r"El error más común: \1",
        ),
        (
            r"^la mayoría(?: de la gente)? (?:comete|hace|tiene) el (?:mismo|gran) error(?: cuando| al)? (.+)$",
            r"El error más común: \1",
        ),
        (
            r"^nadie te (?:ensena|enseña|ensenan|enseñan|ensenar|enseñar|dice|dicen|cuenta|cuentan)(?: que)? (.+)$",
            r"Lo que nadie te dice: \1",
        ),
        (
            r"^nadie (?:quiere|va a) (?:decir|admitir)(?: que)? (.+)$",
            r"Nadie quiere admitirlo: \1",
        ),
        (
            r"^la conclusion es(?: simple| clara)?[:\s]+(.+)$",
            r"\1: la conclusión que cambia todo",
        ),
        (
            r"^la conclusión es(?: simple| clara)?[:\s]+(.+)$",
            r"\1: la conclusión que cambia todo",
        ),
        (r"^esto es (.+)$", r"\1"),
        (r"^aqui esta (.+)$", r"\1"),
        (r"^aquí está (.+)$", r"\1"),
        (r"^resulta que (.+)$", r"\1"),
        (r"^la verdad es(?: que)? (.+)$", r"La verdad: \1"),
        (r"^el problema es(?!\s+no\b)(?: que)? (.+)$", r"El problema: \1"),
        (
            r"^lo que nadie te (?:dice|cuenta) es(?: que)? (.+)$",
            r"Lo que nadie te dice: \1",
        ),
    ),
    "en": (
        (r"^here is (why|how|what) (.+)$", r"\1 \2"),
        (r"^this is (why|how|what) (.+)$", r"\1 \2"),
        (r"^the (?:thing|point) is(?: that)? (.+)$", r"\1"),
        (r"^the truth is(?!\s+not\b)(?: that)? (.+)$", r"The truth: \1"),
        (r"^the problem is(?!\s+not\b)(?: that)? (.+)$", r"The problem: \1"),
        (
            r"^what nobody tells you is(?: that)? (.+)$",
            r"What nobody tells you: \1",
        ),
        (r"^nobody tells you(?: that)? (.+)$", r"What nobody tells you: \1"),
        (
            r"^the conclusion is(?: simple| clear)?[:\s]+(.+)$",
            r"\1: the conclusion that changes everything",
        ),
        (r"^it turns out(?: that)? (.+)$", r"\1"),
        (r"^you know(?: that)? (.+)$", r"\1"),
    ),
}


_LEADIN_PATTERNS: tuple[str, ...] = (
    r"^(?:bueno|pues|vale|okay|ok|este|eh|em|um|uh|so|well|and|y|pero|but)\b[\s,]+",
    r"^(?:mira|escucha|oye|look|listen)\b[\s,]+",
    r"^(?:basicamente|básicamente|literally|en realidad|actually|basically)\b[\s,]+",
    r"^(?:esto es|esto|esta es|estos son|estas son|aqui esta|aquí está|this is|here is)\b[\s,]+",
    r"^(?:la cosa es|the thing is)\b[\s,]+",
    r"^(?:en este video|in this video)\b[\s,]+",
    r"^(?:hoy|today)(?:\s+(?:os|les|te|nos|i|we))?\s+(?:voy|vamos|van|am|are|is)\s+a\s+(?:contar|hablar|decir|mostrar|tell|talk|show)\b[\s,]+",
    r"^(?:os|les|te|nos|i|we)\s+(?:voy|vamos|am|are)\s+a\s+(?:contar|hablar|decir|mostrar|tell|talk|show)\b[\s,]+",
    r"^(?:voy a|vamos a|i(?:'m| am) going to|we(?:'re| are) going to)\s+(?:contar|hablar|decir|mostrar|tell|talk|show)\b[\s,]+",
    r"^(?:les voy a (?:decir|contar)|te voy a (?:decir|contar)|i(?:'m| am) going to (?:tell|show) you|let me (?:tell|show) you)\b[\s,]+",
    r"^(?:y|and|pero|but|entonces|so|then|ademas|also)\b[\s,]+",
)


def _apply_special_rewrite(text: str, language: str) -> str:
    for pattern, replacement in _SPECIAL_REWRITES.get(language, ()):
        match = re.match(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        if language == "es" and replacement.startswith("Lo que nadie te dice"):
            rest = match.group(1).strip()
            if _norm(rest).startswith("como "):
                return "Cómo " + rest[5:]
        return match.expand(replacement)
    return ""


def _strip_leadin(text: str) -> str:
    for _ in range(3):
        before = text
        for pattern in _LEADIN_PATTERNS:
            text = re.sub(pattern, "", text, count=1, flags=re.IGNORECASE).strip()
        if text == before:
            break
    text = re.sub(r"^(?:que|that)\b[\s,]+", "", text, count=1, flags=re.IGNORECASE)
    return _clean_text(text)


def _rewrite_sentence(text: str, language: str) -> str:
    text = _clean_text(text)
    rewritten = _apply_special_rewrite(text, language)
    if rewritten:
        text = rewritten
    else:
        text = _strip_leadin(text)
    text = _strip_tail(_clean_text(text))
    if not text:
        return ""
    if "?" in text or text.startswith("¿"):
        return _question(text, language)
    return _capitalize(text)


def _phrase_runs(text: str) -> list[str]:
    tokens = _tokens(text)
    runs: list[str] = []
    current: list[str] = []

    def close() -> None:
        nonlocal current
        while current and _token_norm(current[0]) in _SOFT:
            current.pop(0)
        while current and _token_norm(current[-1]) in _SOFT:
            current.pop()
        if current and any(_is_content(token) for token in current):
            runs.append(" ".join(current))
        current = []

    for token in tokens:
        if _is_content(token):
            if len(current) >= 8:
                close()
            current.append(token)
        elif _token_norm(token) in _SOFT and current:
            current.append(token)
        else:
            close()
    close()
    return runs


def _topic_candidates(texts: list[str], limit: int = 4) -> list[str]:
    frequency: Counter[str] = Counter()
    for text in texts:
        for token in _tokens(text):
            if _is_content(token):
                frequency[_token_norm(token)] += 1

    scored: dict[str, tuple[float, str]] = {}
    for text in texts:
        for run in _phrase_runs(text):
            content = [
                _token_norm(token) for token in run if _is_content(token)
            ]
            if not content or all(token in _BANAL for token in content):
                continue
            # Corrupted ASR phrases never make a title, no matter how
            # often they repeat inside the clip.
            if _is_garbled(" ".join(run)):
                continue
            if len(content) == 1 and content[0] in _QUESTION_WORDS:
                continue
            # A single common verb is not a subject.
            if len(content) == 1 and content[0] in _VERBS:
                continue
            score = sum(1.0 + 0.25 * (frequency[token] - 1) for token in content)
            score += 0.45 * min(5, len(content))
            score += 1.4 * len(_category_hits(" ".join(run)))
            if any(any(char.isdigit() for char in token) for token in run):
                score += 0.7
            if any(token[0].isupper() for token in run[1:]):
                score += 0.5
            if len(content) == 1 and frequency[content[0]] == 1:
                score -= 1.1
            key = _norm(" ".join(run))
            if not key or len(key) < 3:
                continue
            if key not in scored or score > scored[key][0]:
                scored[key] = (score, _clean_text(" ".join(run)))
    ordered = sorted(scored.values(), key=lambda item: item[0], reverse=True)
    return [phrase for _, phrase in ordered[:limit]]


def _sentence_score(text: str, frequency: Counter[str]) -> float:
    content = _content_tokens(text)
    if len(content) < 2:
        return -8.0
    base = sum(1.0 + 0.22 * min(1.2, frequency[token] - 1) for token in content)
    base /= max(1.0, len(content) ** 0.35)
    base += 0.65 * min(5, len(content))
    base += 1.35 * len(_category_hits(text))
    if re.search(r"\d", text):
        base += 0.6
    if "?" in text or text.startswith("¿"):
        base += 0.7
    if _has_punch(text):
        base += 0.6
    if len(content) > 26:
        base -= 1.0
    normalized = _norm(text)
    if normalized.startswith(
        (
            "y ",
            "and ",
            "pero ",
            "but ",
            "entonces ",
            "so ",
            "hoy ",
            "today ",
            "hola",
            "bienvenidos",
            "hey ",
            "what's up",
            "en el video",
            "in this video",
        )
    ):
        base -= 2.0
    if "voy a contar" in normalized or "going to tell" in normalized:
        base -= 2.0
    if normalized.startswith(("yo ", "i ")):
        base -= 0.5
    base += _garble_penalty(text)
    return base


def _has_punch(text: str) -> bool:
    normalized = _norm(text)
    return any(marker in normalized for marker in _PUNCH)


_CLUSTER = re.compile(r"[bcdfghjklmnpqrstvwxyz]{3,}", re.IGNORECASE)


def _nonword_tokens(text: str) -> list[str]:
    """Content tokens with consonant clusters Spanish/English never has.

    Whisper on noisy game audio invents tokens like "zorblk" or "wexndr";
    real words in either language almost never carry three consonants in a
    row inside a token, so this flags corruption without a dictionary.
    """
    flagged: list[str] = []
    for token in _content_tokens(text):
        if len(token) > 2 and _CLUSTER.search(token):
            flagged.append(token)
    return flagged


def _is_looped(text: str) -> bool:
    """True when the same bigram repeats enough to be an ASR loop."""
    words = _tokens(text)
    if len(words) < 6:
        return False
    bigrams = Counter(zip(words[:-1], words[1:]))
    return max(bigrams.values(), default=0) >= 3


def _garble_penalty(text: str) -> float:
    penalty = -3.5 * min(2, len(_nonword_tokens(text)))
    if _is_looped(text):
        penalty -= 6.0
    return penalty


def _is_garbled(text: str) -> bool:
    return len(_nonword_tokens(text)) >= 2 or _is_looped(text)


def _candidate_score(
    title: str,
    base: float,
    first_norm: str,
) -> float:
    normalized = _norm(title)
    score = base
    if normalized == first_norm:
        score -= 7.0
    if len(title) < 15:
        score -= 2.0
    if len(title) > _MAX_TITLE:
        score -= 9.0
    if 20 <= len(title) <= 66:
        score += 1.0
    if _has_punch(title):
        score += 0.7
    if "?" in title:
        score += 0.3
    if normalized.startswith(("esto ", "this ", "here ", "you know", "la cosa ")):
        score -= 2.0
    last = _token_norm(title.split()[-1]) if title.split() else ""
    if last in _CONNECTORS or last in _FILLERS:
        score -= 2.0
    return score


def _maybe_punch(title: str, category: str, language: str) -> str:
    if "?" in title or _has_punch(title):
        return title
    title = _strip_tail(title).rstrip(" .,;:-")
    suffix = {
        "es": {
            "consejo": ": el consejo que sí funciona",
            "dinero": ": lo que nadie te cuenta",
            "curiosidad": ": lo que nadie te cuenta",
            "historia": ": la historia que cambió todo",
            "conflicto": ": el problema que nadie ve",
            "datos": ": el dato que lo explica todo",
            "emocion": ": la reacción que nadie esperaba",
            "humor": ": el momento más divertido",
        },
        "en": {
            "consejo": ": the advice that actually works",
            "dinero": ": what nobody tells you",
            "curiosidad": ": what nobody tells you",
            "historia": ": the story that changed everything",
            "conflicto": ": the problem nobody sees",
            "datos": ": the detail that explains it all",
            "emocion": ": the reaction nobody expected",
            "humor": ": the funniest moment",
        },
    }.get(language, {}).get(category, "")
    if not suffix or len(title) + len(suffix) > _MAX_TITLE:
        return title
    return title + suffix


def _meta_fallback(meta: dict[str, Any] | None, language: str) -> str:
    source = meta or {}
    game = _clean_text(str(source.get("game") or ""))
    streamer = _clean_text(
        str(source.get("streamer") or source.get("channel") or "")
    )
    if language == "en":
        if game:
            return f"The key moment in {game}"
        if streamer:
            return f"The key moment from {streamer}"
        return "Highlight moment"
    if game:
        return f"El momento clave en {game}"
    if streamer:
        return f"El momento clave de {streamer}"
    return "Momento destacado"


def _polish_title(title: str, language: str) -> str:
    title = _strip_tail(_clean_text(title))
    if not title:
        return ""
    if "?" in title or title.startswith("¿"):
        title = _question(title, language)
    else:
        title = _capitalize(_strip_tail(title).rstrip(" .,;:-"))
    title = re.sub(r"\s+", " ", title).strip()
    if len(title) > _MAX_TITLE:
        title = title[:_MAX_TITLE].rsplit(" ", 1)[0].rstrip(" ,.;:-") + "…"
    return title


def _with_game(title: str, meta: dict[str, Any] | None, language: str) -> str:
    source = meta or {}
    game = _clean_text(str(source.get("game") or ""))
    if not game or _norm(game) in _norm(title):
        return title
    suffix = f" en {game}" if language == "es" else f" in {game}"
    if len(title) + len(suffix) > _MAX_TITLE:
        return title
    if title.endswith("?"):
        return title[:-1] + suffix + "?"
    return title + suffix


def build_clip_title(
    window_sentences: Iterable[Any],
    *,
    language: str | None = None,
    meta: dict[str, Any] | None = None,
) -> str:
    """Build a short, relevant title from the whole clip window.

    The opening line is deliberately not privileged. Sentences are scored
    against keywords that repeat across the clip, then rewritten to remove
    stream-of-consciousness lead-ins. Templates are only a fallback when no
    sentence survives with a usable subject.
    """
    texts = _sentence_texts(window_sentences)
    detected_language = _language(language, " ".join(texts))
    if not texts:
        return _meta_fallback(meta, detected_language)

    first_norm = _norm(texts[0])
    frequency: Counter[str] = Counter()
    for text in texts:
        for token in _content_tokens(text):
            frequency[token] += 1

    full_text = " ".join(texts)
    categories = _category_hits(full_text)
    category = categories[0] if categories else "generic"
    topics = _topic_candidates(texts)
    candidates: list[tuple[float, str]] = []

    for text in texts:
        base = _sentence_score(text, frequency)
        rewritten = _rewrite_sentence(text, detected_language)
        if not rewritten or len(_tokens(rewritten)) < 2:
            continue
        bonus = 0.35 if _norm(rewritten) != _norm(_clean_text(text)) else 0.0
        if "?" in rewritten:
            bonus += 0.25
        candidates.append((base + bonus, rewritten))

    patterns = _PATTERNS.get(detected_language, _PATTERNS["en"])
    best_base = max(
        (_sentence_score(text, frequency) for text in texts), default=1.0
    )
    category_terms = {
        _norm(term)
        for term in _CATEGORY_TERMS.get(category, ())
        if " " not in term.strip()
    }
    usable_topics = [
        topic for topic in topics if _norm(topic) not in category_terms
    ]
    if not usable_topics:
        usable_topics = topics
    for index, topic in enumerate(usable_topics[:3] if not candidates else []):
        for pattern in patterns.get(category) or patterns["generic"]:
            candidates.append(
                (best_base * 0.82 - index * 0.25, pattern.format(topic=topic))
            )
        for pattern in patterns["generic"]:
            candidates.append(
                (best_base * 0.76 - index * 0.25, pattern.format(topic=topic))
            )

    if not candidates:
        return _meta_fallback(meta, detected_language)

    ranked = sorted(
        (
            (_candidate_score(title, score, first_norm), title)
            for score, title in candidates
        ),
        key=lambda item: item[0],
        reverse=True,
    )
    chosen = ranked[0][1]
    if _norm(chosen) == first_norm:
        for _, alternative in ranked[1:]:
            if _norm(alternative) != first_norm:
                chosen = alternative
                break
    # A garbled winner is not a title; the streamer/game fallback reads
    # better than Whisper noise.
    if _is_garbled(chosen):
        fallback = _meta_fallback(meta, detected_language)
        if fallback and fallback != chosen:
            return fallback
    chosen = _with_game(chosen, meta, detected_language)
    chosen = _polish_title(chosen, detected_language)
    if not chosen:
        chosen = _meta_fallback(meta, detected_language)
    return chosen


def is_weak_title(title: str, first_sentence: str) -> bool:
    """True when a model-provided title is just the opening line or a stub."""
    title = str(title or "").strip()
    if not title:
        return True
    normalized = _norm(title)
    if not normalized:
        return True
    if normalized == _norm(first_sentence):
        return True
    if len(_tokens(title)) <= 2:
        return True
    if normalized in _QUESTION_WORDS:
        return True
    return False




