from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator


class AISettingsInput(BaseModel):
    provider: Literal["heuristic", "openrouter", "gemini", "ollama", "custom"]
    model: str = Field(default="", max_length=160)
    base_url: str = Field(default="", max_length=500)
    api_key: str | None = Field(default=None, max_length=1000)
    clear_key: bool = False

SubtitleStyle = Literal[
    "shorts", "bold", "clean", "neon", "minimal", "impact", "pill", "box", "yellow"
]
SUBTITLE_STYLES: tuple[str, ...] = (
    "shorts",
    "bold",
    "clean",
    "neon",
    "minimal",
    "impact",
    "pill",
    "box",
    "yellow",
)
LayoutMode = Literal[
    "auto",
    "vertical",
    "split",
    "centrado",
    "horizontal",
    "dividido",
    "trio",
    "cuarteto",
    "cam_juego",
    "dos_cams_juego",
    "tres_cams_juego",
    "trio_juego",
    "spotlight",
]
LAYOUT_MODES: tuple[str, ...] = (
    "auto",
    "vertical",
    "split",
    "centrado",
    "horizontal",
    "dividido",
    "trio",
    "cuarteto",
    "cam_juego",
    "dos_cams_juego",
    "tres_cams_juego",
    "trio_juego",
    "spotlight",
)
TitleCardStyle = Literal["impact", "clean", "box"]
TitleCardPosition = Literal["top", "center", "bottom"]


class ExportSettings(BaseModel):
    aspect: Literal["9:16", "1:1", "16:9"] = "9:16"
    caption_font: str = Field(default="", max_length=60, pattern=r"^[\w .-]*$")
    caption_color: str = Field(default="", pattern=r"^(#[0-9a-fA-F]{6})?$")
    accent_color: str = Field(default="", pattern=r"^(#[0-9a-fA-F]{6})?$")
    music_level: float | None = Field(default=None, ge=0, le=1)
    saturation: float = Field(default=1, ge=0, le=2)
    platform: Literal["universal","tiktok","shorts","instagram","facebook"] = "universal"
    sound_accent: bool = False
    logo_id: str = Field(default="", pattern=r"^([a-f0-9]{32})?$")
    transition: Literal["cut","fade"] = "cut"
    brand_text: str = Field(default="", max_length=48)


class ClipOptions(ExportSettings):
    use_creator_profile: bool = False
    max_clips: int | None = Field(default=None, ge=5, le=15)
    subtitle_style: SubtitleStyle = "shorts"
    remove_silences: bool = True
    dynamic_zoom: bool = True
    language: str | None = Field(default=None, max_length=12)
    layout: LayoutMode = "auto"
    context_overlay: bool = True
    title_card: str = Field(default="", max_length=120)
    title_card_seconds: float = Field(default=4.0, ge=0.5, le=15.0)
    title_card_position: TitleCardPosition = "top"
    title_card_style: TitleCardStyle = "impact"

    @classmethod
    def from_raw(cls, raw: str | None) -> "ClipOptions":
        if not raw:
            return cls()
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return cls()
        if not isinstance(data, dict):
            return cls()
        allowed = set(cls.model_fields)
        filtered = {key: value for key, value in data.items() if key in allowed}
        try:
            return cls(**filtered)
        except ValidationError:
            return cls()


class SubtitleCueInput(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    text: str = Field(min_length=1, max_length=300)


class SubtitlesInput(BaseModel):
    cues: list[SubtitleCueInput] = Field(min_length=1, max_length=250)


class JobCreateOptions(BaseModel):
    options: ClipOptions = Field(default_factory=ClipOptions)


class PublishClipInput(BaseModel):
    platform: Literal["youtube", "tiktok"]


class TikTokGrabInput(BaseModel):
    url: str = Field(min_length=1, max_length=500)
    title: str = Field(default="", max_length=100)
    auto_publish: bool = True


class TikTokRetryInput(BaseModel):
    auto_publish: bool | None = None


class LiveSessionInput(BaseModel):
    url: str = Field(min_length=1, max_length=500)


class LiveClipInput(BaseModel):
    seconds: int = Field(default=30, ge=5, le=120)


class ClipCopyInput(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(max_length=5000)
    caption: str = Field(max_length=2200)

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("El título no puede estar vacío.")
        return value


class CameraBox(BaseModel):
    """A facecam panel drawn by hand, normalised to the source frame."""

    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    w: float = Field(gt=0.0, le=1.0)
    h: float = Field(gt=0.0, le=1.0)


class ClipEditInput(ExportSettings):
    subtitle_style: SubtitleStyle = "shorts"
    layout: LayoutMode = "auto"
    remove_silences: bool = True
    dynamic_zoom: bool = True
    context_overlay: bool = True
    title_card: str = Field(default="", max_length=120)
    title_card_seconds: float = Field(default=4.0, ge=0.5, le=15.0)
    title_card_position: TitleCardPosition = "top"
    title_card_style: TitleCardStyle = "impact"
    # Empty means "detect the cameras automatically". When present, these
    # boxes replace detection for the camera slots of the chosen template.
    manual_cams: list[CameraBox] = Field(default_factory=list, max_length=4)


class PublishingSettingsInput(BaseModel):
    youtube_client_id: str | None = Field(default=None, max_length=300)
    youtube_client_secret: str | None = Field(default=None, max_length=300)
    tiktok_client_key: str | None = Field(default=None, max_length=300)
    tiktok_client_secret: str | None = Field(default=None, max_length=300)
    redirect_port: int | None = Field(default=None, ge=1024, le=65535)
    youtube_privacy: Literal["private", "unlisted", "public"] | None = None
    tiktok_privacy: Literal[
        "PUBLIC_TO_EVERYONE",
        "MUTUAL_FOLLOW_FRIENDS",
        "FOLLOWER_OF_CREATOR",
        "SELF_ONLY",
    ] | None = None


def serialize_options(options: ClipOptions) -> dict[str, Any]:
    return options.model_dump()
