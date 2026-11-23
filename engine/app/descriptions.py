from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable

from .signals import CATEGORY_INFO, category_hashtag

# A publication has two faces: the long description used by YouTube and the
# short caption used by TikTok/Reels.  Both are generated from the same
# evidence so a clip never gets a description that is only its title.

_FILLERS = frozenset(
    """
    bueno pues vale ok okay este eh em um uh esto esto es o sea digamos
    básicamente basicamente literally like you know i mean
    """.split()
)

_PROBLEM_MARKERS = (
    "no puede",
    "no se",
    "no lo",
    "no me",
    "nunca",
    "imposible",
    "problema",
    "error",
    "fallo",
    "falla",
    "peor",
    "raro",
    "rara",
    "lío",
    "lio",
    "discusión",
    "discusion",
    "pierde",
    "muere",
    "se queda",
    "no entiendo",
    "no te das cuenta",
    "adicto",
    "vicio",
    "prohibido",
    "peligro",
    "denuncia",
    "broma",
    "insulto",
    "grita",
    "cabre",
    "enfad",
    "gente",
    "tonta",
    "tonto",
    "niños",
    "ninos",
    "mierda",
    "puta",
    "joder",
    "coño",
    "cono",
    "hostia",
    "flip",
    "alucin",
    "wtf",
    "imbecil",
    "idiota",
    "estupido",
    "wrong",
    "problem",
    "mistake",
    "fail",
    "never",
    "impossible",
    "weird",
    "idiot",
    "stupid",
    "addict",
    "banned",
    "caught",
)

_PREFIX_MARKERS = (
    "cabre",
    "enfad",
    "grit",
    "insult",
    "problem",
    "mistak",
    "addict",
    "alucin",
)

_TITLE_STOPWORDS = frozenset(
    """
    a al algo como con de del el ella en es esa ese eso esta este esto la las
    lo los mas me mi mis no nos o para pero por que se si sin su sus te tu tus
    un una uno y ya uy eh ah oh
    """.split()
)

_COMMON_WORDS = frozenset(
    """
    a al algo algun alguna algunos ante antes aqui asi aunque bien cada casi como con contra cual
    cuando de del desde donde durante e el ella ellas ellos en entre era eran eres es esa esas ese eso esos
    esta estaba estado estamos estan estas este esto estos estoy fue fueron ha haber habia han hasta hay la las
    le les lo los mas me mi mientras mis mucho muy nada ni no nos nosotros o os otra otro para pero poco por
    porque que quien quienes se sea segun ser si sin sobre son su sus tambien tan te tengo tiene tienen todo todos
    tu tus un una uno unos vosotros y ya yo
    abrir acabar acaso accion aceptar acompanar acercar aconsejar acordar agarrar aguantar ahi ahora alguno amar
    andar ano anos aparecer aprender arreglar asegurar ayudar bailar bajar beber buscar caber caer cambiar caminar
    cansar cantar caro casa cerrar chico chica claro cocinar coger comenzar comer comprar contar contento creer
    correr cosa cosas cuenta cuentas cuerpo dar deber decir dejar demas dentro derecho despues dia dias dificil
    dinero dormir dos duro echar ejemplo empezar encontrar entender entrar enviar escuchar esperar estar facil
    faltar familia favor feliz fin final fondo forma frase fuera gente gratis grande gracias guapo gustar hablar
    hacer historia hora horas igual importante imposible intentar ir juego juegos juntos jugar juro leer levantar
    llamar llegar llevar loco loca luego lugar mal malo manera mano mejor menor menos mentira mirar mismo momento
    mundo mujer muerto nadie natural necesario negro nino ninos nina ninas nuevo nunca ojo otro padre pajaro
    palabra papas parte pasado pasar paz peor pequeno pensar perder persona personas poder poner posible precio
    pregunta preparar presentar primero probar problema problemas producir pueblo pude pudo quedar querer quitar
    raro rara razon recibir reir repetir responder rojo romper saber salir saludar seguir sentir siempre sitio
    solo sonreir suave subir suceder supuesto tarde tener terminar tonto tonta tomar trabajar traer tratar tres
    tipo tipos verdad ver vestir viaje vida video videos viejo venir volver voz
    the a an and or but if then than that this these those in on at to of for with from by as is are was were be
    been being it its i you he she we they my your his her our their not no do does did have has had can could
    would should will may might must what why how who when where people person persons thing things time hour hours
    minute minutes day days week weeks month months year years life world house work money water food game games
    phone mobile app application internet account accounts user users kid kids child children friend friends family
    mother father brother sister woman man boy girl guy guys problem problems error errors part place way case
    moment true truth lie shit fuck damn weird strange crazy good bad better worse big small new old first last
    same different important impossible possible easy hard free expensive cheap much little all nothing more less
    very well badly here there now later after before always never also neither maybe almost still while when
    where like because without about between until since against according during through
    google chrome youtube tiktok instagram whatsapp snapchat roblox gta twitch discord facebook twitter
    verificacion
    """.split()
)

_TIME_TOPIC_WORDS = (
    "tiempo",
    "uso",
    "hora",
    "horas",
    "minuto",
    "minutos",
    "dia",
    "dias",
    "semana",
    "semanas",
    "mes",
    "meses",
    "ano",
    "anos",
    "time",
    "usage",
    "hour",
    "hours",
    "minute",
    "minutes",
    "day",
    "days",
    "week",
    "weeks",
)

_FILLER_TAIL_RE = re.compile(
    r"\b(?:eh|no|verdad|sabes|entiendes|right|okay|ok)\s*[?!.]*$",
    re.IGNORECASE,
)

_PAYOFF_MARKERS = (
    "al final",
    "resultado",
    "termina",
    "acaba",
    "conclusión",
    "conclusion",
    "por eso",
    "así que",
    "asi que",
    "lo mejor",
    "lo que destaca",
    "increíble",
    "increible",
    "no me lo puedo creer",
    "no puede ser",
    "de repente",
    "de la nada",
    "en el último",
    "en el ultimo",
    "in the end",
    "result",
    "turns out",
    "that's why",
    "so",
    "unbelievable",
    "crazy",
    "insane",
    "the best",
)

_TIME_RE = re.compile(
    r"(?<![\w])(\d{1,4}(?:[.,]\d+)?)\s*"
    r"(horas?|h|minutos?|min|d[ií]as?|semanas?|mes(?:es)?|años?|"
    r"hours?|hrs?|minutes?|mins?|days?|weeks?|months?|years?)(?![\w])",
    re.IGNORECASE,
)

_SPANISH_NUMBERS = {
    "un": "1",
    "una": "1",
    "dos": "2",
    "tres": "3",
    "cuatro": "4",
    "cinco": "5",
    "seis": "6",
    "siete": "7",
    "ocho": "8",
    "nueve": "9",
    "diez": "10",
    "once": "11",
    "doce": "12",
    "trece": "13",
    "catorce": "14",
    "quince": "15",
    "dieciseis": "16",
    "diecisiete": "17",
    "dieciocho": "18",
    "diecinueve": "19",
    "veinte": "20",
    "veintiun": "21",
    "veintiuno": "21",
    "veintidos": "22",
    "veintitres": "23",
    "veinticuatro": "24",
    "veinticinco": "25",
    "veintiseis": "26",
    "veintisiete": "27",
    "veintiocho": "28",
    "veintinueve": "29",
    "treinta": "30",
    "cuarenta": "40",
    "cincuenta": "50",
    "sesenta": "60",
    "setenta": "70",
    "ochenta": "80",
    "noventa": "90",
    "cien": "100",
    "ciento": "100",
}
_WORD_TIME_RE = re.compile(
    r"(?<![\w])("
    + "|".join(_SPANISH_NUMBERS)
    + r")\s+(horas?|minutos?|d[ií]as?|semanas?|mes(?:es)?|años?)(?![\w])",
    re.IGNORECASE,
)
_PERCENT_RE = re.compile(r"(?<![\w])(\d{1,3}(?:[.,]\d+)?)\s*%")

_APP_NAMES = {
    "roblox": "Roblox",
    "tiktok": "TikTok",
    "youtube": "YouTube",
    "instagram": "Instagram",
    "whatsapp": "WhatsApp",
    "snapchat": "Snapchat",
    "discord": "Discord",
    "twitch": "Twitch",
    "kick": "Kick",
    "chrome": "Chrome",
    "google": "Google",
    "minecraft": "Minecraft",
    "fortnite": "Fortnite",
    "gta": "GTA",
    "free fire": "Free Fire",
    "clash royale": "Clash Royale",
    "brawl stars": "Brawl Stars",
    "among us": "Among Us",
}
_APP_RE = re.compile(
    r"(?<![\w])(" + "|".join(re.escape(name) for name in _APP_NAMES) + r")(?![\w])",
    re.IGNORECASE,
)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+|\n+")
_WORD_RE = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9]+")

_SPANISH_HINTS = frozenset(
    "que de la el y en no es un una pero como más mas por para con se lo su al del".split()
)
_ENGLISH_HINTS = frozenset(
    "the and to of a in is it you that but like this for with on was are".split()
)

_CATEGORY_ES = {
    "angry": (
        "un momento en el que pierde la paciencia",
        "la reacción de {streamer} cuando ya no puede más",
    ),
    "funny": (
        "una situación que se le va de las manos",
        "la reacción de {streamer} y las caras que pone",
    ),
    "crazy_reactions": (
        "una reacción que se descontrola",
        "la cara de {streamer} cuando ve lo que pasa",
    ),
    "epic": (
        "una jugada que parecía perdida",
        "el momento exacto en el que todo cambia",
    ),
    "unexpected": (
        "un giro que nadie ve venir",
        "el momento en el que todo da un vuelco",
    ),
    "scary": (
        "algo que no esperaba ver",
        "lo que aparece después y cómo reacciona {streamer}",
    ),
    "fails": (
        "un fallo que no esperaba",
        "la reacción de {streamer} después del fallo",
    ),
    "wins": (
        "un reto que parecía imposible",
        "la jugada que lo resuelve todo",
    ),
    "drama": (
        "una discusión que sube de tono",
        "el momento en el que la tensión se corta",
    ),
    "shocking": (
        "un dato que deja a todos en shock",
        "la reacción de {streamer} al escucharlo",
    ),
}

_CATEGORY_EN = {
    "angry": ("a moment where patience runs out", "the reaction when it finally boils over"),
    "funny": ("a situation that gets out of hand", "the reaction and the faces that come with it"),
    "crazy_reactions": ("a reaction that spirals", "the look on {streamer}'s face"),
    "epic": ("a play that looked lost", "the exact moment everything flips"),
    "unexpected": ("a twist nobody sees coming", "the moment everything turns around"),
    "scary": ("something nobody expected to see", "what appears next and how {streamer} reacts"),
    "fails": ("a failure nobody saw coming", "the reaction right after the fall"),
    "wins": ("a challenge that looked impossible", "the play that solves it"),
    "drama": ("an argument that escalates", "the moment the tension snaps"),
    "shocking": ("a detail that leaves everyone stunned", "the reaction when it lands"),
}

_CATEGORY_SHORT_ES = {
    "angry": "enfado",
    "funny": "humor",
    "crazy_reactions": "reacción",
    "epic": "momento épico",
    "unexpected": "inesperado",
    "scary": "miedo",
    "fails": "fail",
    "wins": "victoria",
    "drama": "drama",
    "shocking": "shock",
}

_CATEGORY_SHORT_EN = {
    "angry": "angry moment",
    "funny": "funny moment",
    "crazy_reactions": "reaction",
    "epic": "epic moment",
    "unexpected": "unexpected moment",
    "scary": "scary moment",
    "fails": "fail",
    "wins": "win",
    "drama": "drama",
    "shocking": "shocking moment",
}

_GENERIC_SOURCE_TITLES = {
    "video de youtube",
    "youtube video",
    "video",
    "clip",
    "shorts",
    "short",
}


@dataclass(frozen=True)
class Publication:
    description: str
    caption: str


def build_publication(
    *,
    title: str,
    hook: str = "",
    reason: str = "",
    text: str = "",
    sentences: Iterable[str] | None = None,
    category: str = "",
    tags: Iterable[str] | None = None,
    meta: dict[str, Any] | None = None,
    language: str | None = None,
) -> Publication:
    """Create publishable copy using actual sentences, never invented reactions."""
    from .editorial import select_evidence, topical_tags, publication_hashtags

    source = meta or {}
    streamer = _clean_name(source.get("streamer") or source.get("channel") or "")
    game = _clean_name(source.get("game") or "")
    source_title = _clean_source_title(source.get("source_title") or source.get("title") or "")
    lang = _resolve_language(language, text or title)
    evidence = " ".join(str(s) for s in sentences) if sentences else text
    quotes = select_evidence(evidence, title)
    if streamer or source_title:
        attribution = ("Fragmento de " if lang == "es" else "Excerpt from ") + (streamer or source_title) + "."
    else:
        attribution = ""
    body = " ".join(quotes) or title.strip() or ("Momento destacado." if lang == "es" else "Highlight.")
    topics = topical_tags(evidence, game=game, streamer=streamer, tags=tags or ())
    description = "\n\n".join(filter(None, (body, attribution, publication_hashtags(topics, "youtube"))))
    caption_body = quotes[0] if quotes else body
    caption = "\n\n".join(filter(None, (caption_body, publication_hashtags(topics, "tiktok"))))
    return Publication(description=description, caption=caption)


def _resolve_language(language: str | None, text: str) -> str:
    value = (language or "").strip().lower()
    if value.startswith("en"):
        return "en"
    if value.startswith("es"):
        return "es"
    words = set(_WORD_RE.findall(_normalize(text)))
    spanish = len(words & _SPANISH_HINTS)
    english = len(words & _ENGLISH_HINTS)
    return "en" if english > spanish else "es"


def _normalize(text: str) -> str:
    value = unicodedata.normalize("NFKD", str(text or ""))
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", value).strip().lower()


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _split_sentences(text: str) -> list[str]:
    value = _collapse(text)
    if not value:
        return []
    return [part.strip() for part in _SENTENCE_SPLIT_RE.split(value) if part.strip()]


def _expand_long_sentences(
    sentences: Iterable[str], max_words: int = 40
) -> list[str]:
    expanded: list[str] = []
    for sentence in sentences:
        value = str(sentence or "").strip()
        if not value:
            continue
        if len(value.split()) <= max_words:
            expanded.append(value)
            continue
        clauses = [
            part.strip()
            for part in re.split(r"(?<=[,;:])\s+", value)
            if part.strip()
        ]
        kept = [clause for clause in clauses if len(clause.split()) >= 5]
        if len(kept) >= 2:
            expanded.extend(kept)
        else:
            expanded.append(value)
    return expanded


_ASR_FIXES = (
    (re.compile(r"\bg[uú]gel\s+croma\b", re.IGNORECASE), "Google Chrome"),
    (re.compile(r"\bg[uú]gel\b", re.IGNORECASE), "Google"),
    (re.compile(r"\btic\s+toco\b", re.IGNORECASE), "TikTok"),
    (re.compile(r"\btik\s*tok\b", re.IGNORECASE), "TikTok"),
)


def _fix_transcript(value: str) -> str:
    result = value
    for pattern, replacement in _ASR_FIXES:
        result = pattern.sub(replacement, result)
    return result


def _clean_sentence(text: str) -> str:
    value = _collapse(text)
    value = re.sub(
        r"^(?:bueno|pues|vale|ok|okay|este|eh|em|um|uh|so|well|and|y|pero)[, ]+",
        "",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(r"\b(\w+)(?:\s+\1\b)+", r"\1", value, flags=re.IGNORECASE)
    value = value.strip(" ,;:-")
    value = re.sub(r"\s+([,.!?…])", r"\1", value)
    value = _fix_transcript(value)
    if value and value[-1] not in ".!?…":
        value += "."
    return _capitalize_first(value)


def _capitalize_first(text: str) -> str:
    value = str(text or "")
    if not value:
        return value
    if value[0] in "¿¡" and len(value) > 1 and value[1].islower():
        return value[0] + value[1].upper() + value[2:]
    if value[0].islower():
        return value[0].upper() + value[1:]
    return value


def _unique_sentences(sentences: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for sentence in sentences:
        key = " ".join(_WORD_RE.findall(_normalize(sentence)))
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(sentence)
    return result


def _usable_sentence(sentence: str) -> bool:
    words = _WORD_RE.findall(sentence)
    if len(words) < 4:
        return False
    content = [word for word in words if _normalize(word) not in _FILLERS]
    if len(content) < 3:
        return False
    if len(sentence) < 18:
        return False
    # Lines that are only names, laughter or a single repeated token do not make
    # a useful description, even when the transcript is noisy.
    if len(set(_normalize(word) for word in content)) < 3:
        return False
    return True


def _clean_name(value: Any) -> str:
    text = _collapse(str(value or ""))
    text = re.sub(r"^[@#]+", "", text)
    return text[:60].strip()


def _sentence_case(text: str) -> str:
    value = _collapse(text)
    if not value:
        return ""
    letters = [char for char in value if char.isalpha()]
    if letters and sum(char.isupper() for char in letters) / len(letters) > 0.7:
        value = value.lower()
    if value and value[0].islower():
        value = value[0].upper() + value[1:]
    return value


def _clean_source_title(value: Any) -> str:
    text = _collapse(str(value or ""))
    if not text:
        return ""
    text = re.sub(r"^[\[(【].*?[\])】]\s*", "", text)
    text = re.sub(r"\s*[|｜]\s*.*$", "", text)
    lower = text.lower()
    for prefix in (
        "reaccionando a los ",
        "reaccionando a las ",
        "reaccionando al ",
        "reaccionando a ",
        "reaccionando ",
        "reaction to ",
        "reacting to ",
        "watching ",
        "mirando ",
        "viendo ",
        "analizando ",
        "probando ",
        "reviewing ",
    ):
        if lower.startswith(prefix):
            text = text[len(prefix) :]
            break
    text = text.strip(" -–—:|")
    text = _sentence_case(text)
    if not text or _normalize(text) in _GENERIC_SOURCE_TITLES:
        return ""
    if len(text.split()) < 2:
        return ""
    return text[:120]


def _time_label(number: str, unit: str) -> str:
    number = number.replace(",", ".")
    unit = unit.lower()
    singular = number in {"1", "1.0"}
    if unit in {"hour", "hours", "hr", "hrs"}:
        unit = "hour" if singular else "hours"
    elif unit in {"minute", "minutes", "mins"}:
        unit = "minute" if singular else "minutes"
    elif unit in {"day", "days"}:
        unit = "day" if singular else "days"
    elif unit in {"week", "weeks"}:
        unit = "week" if singular else "weeks"
    elif unit in {"month", "months"}:
        unit = "month" if singular else "months"
    elif unit in {"year", "years"}:
        unit = "year" if singular else "years"
    elif unit == "h":
        unit = "hora" if singular else "horas"
    elif unit == "min":
        unit = "minuto" if singular else "minutos"
    elif unit.startswith("d"):
        unit = "días" if not singular else "día"
    elif unit.startswith("sem"):
        unit = "semanas" if not singular else "semana"
    elif unit.startswith("mes"):
        unit = "meses" if not singular else "mes"
    elif unit.startswith("a"):
        unit = "años" if not singular else "año"
    return f"{number} {unit}"


def _details_from(text: str) -> list[str]:
    details: list[str] = []
    seen: set[str] = set()

    for match in _TIME_RE.finditer(text):
        try:
            value = float(match.group(1).replace(",", "."))
        except ValueError:
            value = 0.0
        if value == 1:
            continue
        label = _time_label(match.group(1), match.group(2))
        key = _normalize(label)
        if key not in seen:
            seen.add(key)
            details.append(label)

    for match in _WORD_TIME_RE.finditer(text):
        number = _SPANISH_NUMBERS.get(match.group(1).lower(), match.group(1))
        try:
            value = float(number)
        except ValueError:
            value = 0.0
        if value == 1:
            continue
        label = _time_label(number, match.group(2))
        key = _normalize(label)
        if key not in seen:
            seen.add(key)
            details.append(label)

    for match in _PERCENT_RE.finditer(text):
        label = f"{match.group(1)}%"
        key = _normalize(label)
        if key not in seen:
            seen.add(key)
            details.append(label)

    for match in _APP_RE.finditer(text):
        name = _APP_NAMES.get(match.group(1).lower(), match.group(1))
        key = _normalize(name)
        if key not in seen:
            seen.add(key)
            details.append(name)

    # Numbers first: they are the concrete evidence a viewer remembers.
    details.sort(key=lambda item: 0 if _TIME_RE.search(item) or item.endswith("%") else 1)
    return details[:4]


def _time_score(sentence: str, base: float) -> float:
    values: list[float] = []
    for match in _TIME_RE.finditer(sentence):
        try:
            values.append(float(match.group(1).replace(",", ".")))
        except ValueError:
            continue
    for match in _WORD_TIME_RE.finditer(sentence):
        try:
            values.append(float(_SPANISH_NUMBERS.get(match.group(1).lower(), "0")))
        except ValueError:
            continue
    if not values:
        return 0.0
    return base if max(values) >= 2 else min(base, 1.0)


def _has_marker(text: str, markers: Iterable[str]) -> bool:
    normalized = _normalize(text)
    if not normalized:
        return False
    for marker in markers:
        key = _normalize(marker)
        if not key:
            continue
        if key in _PREFIX_MARKERS:
            if re.search(rf"\b{re.escape(key)}", normalized):
                return True
        elif " " in key:
            if key in normalized:
                return True
        elif re.search(rf"\b{re.escape(key)}\b", normalized):
            return True
    return False


def _title_content_tokens(text: str) -> set[str]:
    return {
        word
        for word in _WORD_RE.findall(_normalize(text))
        if word not in _TITLE_STOPWORDS and len(word) >= 2
    }


def _shares_long_ngram(sentence: str, title: str, size: int = 4) -> bool:
    sentence_words = _WORD_RE.findall(_normalize(sentence))
    title_words = _WORD_RE.findall(_normalize(title))
    if len(sentence_words) < size or len(title_words) < size:
        return False
    sentence_ngrams = {
        tuple(sentence_words[index : index + size])
        for index in range(len(sentence_words) - size + 1)
    }
    return any(
        tuple(title_words[index : index + size]) in sentence_ngrams
        for index in range(len(title_words) - size + 1)
    )


def _time_topic(text: str) -> bool:
    normalized = _normalize(text)
    return any(
        re.search(rf"\b{re.escape(word)}\b", normalized)
        for word in _TIME_TOPIC_WORDS
    )


def _people_topic(text: str) -> bool:
    normalized = _normalize(text)
    return ("gente" in normalized or "people" in normalized) and any(
        word in normalized for word in ("rara", "raro", "weird", "strange", "crazy")
    )


def _problem_score(
    sentence: str,
    title_tokens: set[str],
    title_key: str,
    index: int,
    total: int,
    source_title: str = "",
    known_tokens: set[str] | None = None,
    time_bonus: float = 0.5,
) -> float:
    normalized = _normalize(sentence)
    words = _WORD_RE.findall(normalized)
    if not words:
        return -10.0
    score = 0.0
    score += _time_score(sentence, time_bonus)
    if _PERCENT_RE.search(sentence):
        score += time_bonus
    if _has_marker(sentence, _PROBLEM_MARKERS):
        score += 2.5
    if title_tokens:
        overlap = len(set(words) & title_tokens) / max(1, len(title_tokens))
        score += overlap * 5.0
    if 8 <= len(words) <= 30:
        score += 1.5
    elif len(words) > 42:
        score -= 1.5
    if _has_marker(sentence, _PAYOFF_MARKERS):
        score += 0.8
    if total > 1:
        position = index / float(total - 1)
        if 0.12 <= position <= 0.88:
            score += 0.6
    unique_ratio = len(set(words)) / max(1, len(words))
    if unique_ratio < 0.55:
        score -= 2.0
    if sentence.rstrip().endswith(("?", "!")):
        score += 0.8
    if _FILLER_TAIL_RE.search(normalized):
        score -= 0.8
    known = known_tokens or set()
    unknown = [
        word
        for word in words
        if len(word) >= 4
        and not word.isdigit()
        and word not in _COMMON_WORDS
        and word not in known
    ]
    if unknown:
        score -= (len(unknown) / max(1, len(words))) * 4.0
    if " ".join(words) == title_key:
        score -= 8.0
    return score


def _is_quotable(sentence: str) -> bool:
    text = sentence.rstrip()
    if text.endswith(("?", "!")):
        return True
    return _has_marker(sentence, _PROBLEM_MARKERS)


def _pick_problem(
    sentences: list[str],
    title: str,
    lang: str,
    source_title: str = "",
) -> str:
    usable = [sentence for sentence in sentences if _usable_sentence(sentence)]
    if not usable:
        return ""
    title_words = set(_WORD_RE.findall(_normalize(title)))
    title_tokens = _title_content_tokens(title)
    title_key = " ".join(_WORD_RE.findall(_normalize(title)))
    known_tokens = title_tokens | _title_content_tokens(source_title)
    time_bonus = (
        3.0
        if _time_topic(source_title) and not _people_topic(title)
        else 0.5
    )
    scored = [
        (
            _problem_score(
                sentence,
                title_tokens,
                title_key,
                index,
                len(usable),
                source_title,
                known_tokens,
                time_bonus,
            ),
            index,
            sentence,
        )
        for index, sentence in enumerate(usable)
    ]
    scored.sort(key=lambda item: (item[0], -abs(item[1] - len(usable) / 2.0)), reverse=True)
    for score, _, sentence in scored:
        if score < 1.0:
            break
        if not _is_quotable(sentence):
            continue
        if _shares_long_ngram(sentence, title):
            continue
        words = set(_WORD_RE.findall(_normalize(sentence)))
        if title_tokens:
            containment = len(words & title_tokens) / max(1, len(title_tokens))
            if containment >= 0.75 and len(words) <= len(title_words) + 6:
                continue
        quote = _truncate_quote(sentence, 240)
        if quote:
            return quote
    return ""


def _truncate_quote(text: str, limit: int) -> str:
    value = _clean_sentence(text)
    if len(value) <= limit:
        return value
    cut = value[:limit].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return cut + "…"


def _join_es(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " y " + items[-1]


def _join_en(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def _category_short(category: str, lang: str) -> str:
    mapping = _CATEGORY_SHORT_ES if lang == "es" else _CATEGORY_SHORT_EN
    if category in mapping:
        return mapping[category]
    return "momento destacado" if lang == "es" else "highlight"


def _category_pair(category: str, lang: str) -> tuple[str, str]:
    mapping = _CATEGORY_ES if lang == "es" else _CATEGORY_EN
    if category in mapping:
        return mapping[category]
    if lang == "es":
        return ("una situación que llama la atención", "el momento clave del clip")
    return ("a moment worth watching", "the key moment of the clip")


def _problem_detail_for(
    *,
    category: str,
    lang: str,
    reason: str,
    title: str = "",
    problem_quote: str = "",
) -> str:
    problem, _ = _category_pair(category, lang)
    reason_text = _collapse(reason)
    if reason_text and len(reason_text.split()) >= 8:
        normalized = _normalize(reason_text)
        if not any(generic in normalized for generic in ("clip autocontenido", "evento de", "detectado por")):
            # A specific editorial reason is stronger than a bucket template.
            return reason_text.rstrip(".").lower()

    evidence = _normalize(" ".join([title, problem_quote]))
    title_evidence = _normalize(title)
    numbers = [
        detail
        for detail in _details_from(" ".join([title, problem_quote]))
        if _TIME_RE.search(detail)
    ]
    if lang == "es":
        if "gente" in evidence and any(
            word in evidence for word in ("rara", "raro", "tonta", "tonto")
        ):
            return "la gente tan rara que aparece en el clip"
        if any(word in evidence for word in ("imbecil", "idiota")) or (
            "tonto" in evidence and "gente" not in evidence
        ):
            return "el comentario que le sueltan"
        if "quien" in title_evidence and any(
            word in title_evidence for word in ("creado", "creo")
        ):
            return "el origen de lo que aparece en pantalla"
        if any(word in evidence for word in ("mierda", "asco", "puta")):
            return "el contenido que aparece en pantalla"
        if numbers:
            return f"la cifra de {_join_es(numbers[:2])}"
        if _time_topic(title):
            return "la cifra de tiempo que se menciona"
        if "?" in title or "¿" in title:
            return "la pregunta que abre el clip"
        return problem

    if "people" in evidence and any(
        word in evidence for word in ("weird", "strange", "crazy")
    ):
        return "the strange people in the clip"
    if any(word in evidence for word in ("idiot", "stupid", "dumb")):
        return "the comment thrown at them"
    if "who" in title_evidence and any(
        word in title_evidence for word in ("created", "made", "built")
    ):
        return "the origin of what's on screen"
    if any(word in evidence for word in ("shit", "crap", "wtf")):
        return "the content on screen"
    if numbers:
        return f"the number of {_join_en(numbers[:2])}"
    if _time_topic(title):
        return "the time figure mentioned"
    if "?" in title:
        return "the question the clip opens with"
    return problem


def _standout_for(
    *,
    category: str,
    streamer: str,
    game: str,
    details: list[str],
    lang: str,
    reason: str,
    problem_detail: str = "",
) -> str:
    _, template = _category_pair(category, lang)
    name = streamer or ("el creador" if lang == "es" else "the creator")
    standout = template.format(streamer=name)
    numbers = [detail for detail in details if _TIME_RE.search(detail) or detail.endswith("%")]
    normalized = _normalize(problem_detail)

    if lang == "es":
        if normalized.startswith("el comentario"):
            return f"la forma en que {name} responde al comentario"
        if normalized.startswith("el contenido"):
            return f"la reacción de {name} ante lo que aparece en pantalla"
        if normalized.startswith("el origen"):
            return f"la cara de {name} al descubrir el origen"
        if normalized.startswith("la gente"):
            return f"la cara de {name} ante esa gente"
        if normalized.startswith("la cifra") and numbers:
            return f"la reacción de {name} al ver esa cifra"
        if numbers:
            return f"la reacción de {name} al ver esas cifras"
    else:
        if normalized.startswith("the comment"):
            return f"the way {name} responds to the comment"
        if normalized.startswith("the content"):
            return f"{name}'s reaction to what's on screen"
        if normalized.startswith("the origin"):
            return f"{name}'s face when they find out where it came from"
        if normalized.startswith("the strange people"):
            return f"{name}'s face around those people"
        if normalized.startswith("the number") and numbers:
            return f"{name}'s reaction to that number"
        if numbers:
            return f"{name}'s reaction to those numbers"

    if game and "{game}" not in standout:
        if lang == "es":
            return f"{standout} en {game}"
        return f"{standout} in {game}"
    return standout


def _context_line(
    *,
    lang: str,
    streamer: str,
    game: str,
    source_title: str,
    problem_detail: str,
) -> str:
    if lang == "es":
        who = streamer or "el creador"
        where = f" en {game}" if game else ""
        if source_title:
            return (
                f"En este clip de «{source_title}»{where}, {who} se topa con "
                f"{problem_detail}."
            )
        return f"En este clip, {who} se topa con {problem_detail}{where}."
    who = streamer or "the creator"
    where = f" in {game}" if game else ""
    if source_title:
        return (
            f"In this clip from “{source_title}”{where}, {who} runs into "
            f"{problem_detail}."
        )
    return f"In this clip, {who} runs into {problem_detail}{where}."


def _detail_line(*, lang: str, details: list[str], streamer: str) -> str:
    if not details:
        return ""
    numbers = [detail for detail in details if _TIME_RE.search(detail) or detail.endswith("%")]
    if not numbers:
        return ""
    joined = _join_es(numbers[:3]) if lang == "es" else _join_en(numbers[:3])
    if lang == "es":
        who = streamer or "el creador"
        return f"Las cifras que aparecen lo dicen todo: {joined}. {who} no da crédito."
    who = streamer or "the creator"
    return f"The numbers on screen say it all: {joined}. {who} cannot believe it."


def _caption_for(
    *,
    lang: str,
    streamer: str,
    game: str,
    category: str,
    details: list[str],
    standout: str,
    problem_detail: str = "",
    hashtags: str,
) -> str:
    normalized = _normalize(problem_detail)
    if lang == "es":
        who = streamer
        where = f" en {game}" if game else ""
        numbers = [detail for detail in details if _TIME_RE.search(detail)]
        if numbers:
            hook = f"{who or 'Esto'} no se cree lo que ve{where}: {_join_es(numbers[:2])}."
        elif normalized.startswith("el comentario"):
            hook = f"{who or 'Esto'} no se cree el comentario que le sueltan{where}."
        elif normalized.startswith("el origen"):
            hook = f"{who or 'Esto'} no se cree lo que acaba de encontrar{where}."
        elif normalized.startswith("el contenido"):
            hook = f"{who or 'Esto'} no se cree lo que aparece en pantalla."
        elif normalized.startswith("la gente"):
            hook = f"{who or 'Esto'} no se cree la gente tan rara que ve{where}."
        elif who:
            hook = f"{who} no se lo puede creer{where}."
        else:
            hook = f"No te vas a creer lo que pasa{where}."
        body = f"Lo que destaca: {standout}."
    else:
        who = streamer
        where = f" in {game}" if game else ""
        numbers = [detail for detail in details if _TIME_RE.search(detail)]
        if numbers:
            hook = f"{who or 'This'} cannot believe what they see{where}: {_join_en(numbers[:2])}."
        elif normalized.startswith("the comment"):
            hook = f"{who or 'This'} cannot believe the comment thrown at them{where}."
        elif normalized.startswith("the origin"):
            hook = f"{who or 'This'} cannot believe what they just found{where}."
        elif normalized.startswith("the content"):
            hook = f"{who or 'This'} cannot believe what's on screen."
        elif normalized.startswith("the strange people"):
            hook = f"{who or 'This'} cannot believe the people they see{where}."
        elif who:
            hook = f"{who} cannot believe it{where}."
        else:
            hook = f"You won't believe what happens{where}."
        body = f"What stands out: {standout}."
    caption = "\n\n".join(part for part in (hook, body, hashtags) if part)
    if len(caption) > 900:
        caption = caption[:900].rsplit(" ", 1)[0].rstrip(" ,;:-") + "…"
    return caption


def _slug(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^A-Za-z0-9]+", "", text).lower()
    return text[:28]


def _hashtags(
    *,
    lang: str,
    category: str,
    game: str,
    streamer: str,
    tags: Iterable[str],
    platform: str,
) -> str:
    if platform == "youtube":
        items = ["#Shorts", "#YouTubeShorts"]
    else:
        items = ["#tiktok", "#parati" if lang == "es" else "#fyp"]
    if category:
        items.append(category_hashtag(category))
    if game:
        items.append("#" + _slug(game))
    if streamer:
        items.append("#" + _slug(streamer))
    for tag in tags:
        slug = _slug(str(tag))
        if slug:
            items.append("#" + slug)
    items.append("#clips" if platform == "youtube" else "#viral")

    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item.lower()
        if key in seen or len(item) < 3:
            continue
        seen.add(key)
        result.append(item)
    limit = 8 if platform == "youtube" else 5
    return " ".join(result[:limit])
