"""Recognize supported platforms without resolving arbitrary URLs."""
from urllib.parse import urlparse

PLATFORM_LABELS = {"youtube": "YouTube", "kick": "Kick", "twitch": "Twitch"}
REMOTE_SOURCES = frozenset(PLATFORM_LABELS)
_HOSTS = {
    **dict.fromkeys(("youtube.com", "www.youtube.com", "m.youtube.com",
                     "music.youtube.com", "youtu.be", "www.youtu.be"), "youtube"),
    **dict.fromkeys(("kick.com", "www.kick.com"), "kick"),
    **dict.fromkeys(("twitch.tv", "www.twitch.tv", "m.twitch.tv", "go.twitch.tv",
                     "clips.twitch.tv", "player.twitch.tv"), "twitch"),
}


def source_platform(url: str) -> str:
    try:
        parsed = urlparse(url.strip())
        valid = (parsed.scheme in {"http", "https"} and not parsed.username
                 and not parsed.password and parsed.port in {None, 80, 443})
        platform = _HOSTS.get(parsed.hostname or "")
    except ValueError:
        valid, platform = False, None
    if not valid or not platform:
        raise ValueError("Usa un enlace http(s) de YouTube, Kick o Twitch.")
    return platform
