"""Layout templates for vertical clips, modelled on how ViroCut frames a stream.

Every template describes the 1080x1920 canvas as a list of slots. A slot is
either ``cam`` (a detected facecam panel), ``game`` (the animated 9:16 crop of
the scene) or ``full`` (the whole frame, letterboxed or blurred behind).

The templates are pure geometry so they can be tested without touching video.
``render.py`` turns them into pixels.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Templates exposed to the UI. ``split`` is the legacy name for ``cam_juego``
# and stays because existing clips stored it in the database.
TEMPLATES: dict[str, dict[str, Any]] = {
    "vertical": {
        "name": "Vertical",
        "description": "Recorte 9:16 con seguimiento de cara o escena.",
        "cams": (1,),
        "content": True,
    },
    "centrado": {
        "name": "Centrado",
        "description": "El video entero centrado sobre un fondo difuminado.",
        "cams": (1,),
        "content": False,
    },
    "horizontal": {
        "name": "Horizontal",
        "description": "El video completo, con bandas arriba y abajo.",
        "cams": (0,),
        "content": False,
    },
    "dividido": {
        "name": "Dividido",
        "description": "Dos camaras, una encima de la otra.",
        "cams": (2,),
        "content": False,
    },
    "trio": {
        "name": "Trio",
        "description": "Tres camaras apiladas.",
        "cams": (3,),
        "content": False,
    },
    "cuarteto": {
        "name": "Cuarteto",
        "description": "Cuatro camaras en cuadricula.",
        "cams": (4,),
        "content": False,
    },
    "cam_juego": {
        "name": "Camara + juego",
        "description": "Camara arriba, partida abajo.",
        "cams": (1,),
        "content": True,
    },
    "dos_cams_juego": {
        "name": "2 cams + juego",
        "description": "Dos camaras arriba y la partida debajo.",
        "cams": (2,),
        "content": True,
    },
    "tres_cams_juego": {
        "name": "3 cams + juego",
        "description": "Tres camaras arriba y la partida debajo.",
        "cams": (3,),
        "content": True,
    },
    "trio_juego": {
        "name": "Trio con juego",
        "description": "Partida arriba y tres camaras abajo.",
        "cams": (3,),
        "content": True,
    },
    "spotlight": {
        "name": "Spotlight",
        "description": "Lo importante en grande y la escena completa debajo.",
        "cams": (0, 1, 2, 3, 4),
        "content": True,
    },
}

LAYOUT_MODES: tuple[str, ...] = ("auto", *TEMPLATES.keys())
# ``split`` kept as an accepted alias, not advertised in the picker.
_ALIASES = {"split": "cam_juego"}

CANVAS_W = 1080
CANVAS_H = 1920
GAP = 6
DEFAULT_CAM_BAND = 0.30


@dataclass(frozen=True)
class Slot:
    """One panel of the vertical canvas."""

    kind: str  # "cam" | "game" | "full" | "full_blur"
    rect: tuple[int, int, int, int]
    box: tuple[float, float, float, float] | None = None
    pad: bool = False


@dataclass(frozen=True)
class LayoutPlan:
    template: str
    slots: list[Slot] = field(default_factory=list)
    caption_anchor: int | None = None


def normalize_template(value: str | None) -> str:
    raw = str(value or "auto").strip().lower()
    raw = _ALIASES.get(raw, raw)
    return raw if raw in TEMPLATES else "auto"


def choose_template(
    cam_count: int,
    *,
    has_content: bool = False,
    small_cams: bool = False,
) -> str:
    """Pick a template from what the frame actually contains.

    Mirrors ViroCut's rules: webcams that leave room for the scene become a
    camera + game layout, full-frame webcams become a grid, and a single
    small camera over gameplay still gets the scene below it.
    """
    if cam_count <= 0:
        return "vertical"
    if cam_count > 4:
        return "horizontal"
    if has_content:
        if cam_count == 1:
            return "cam_juego" if small_cams else "spotlight"
        if cam_count == 2:
            return "dos_cams_juego"
        if cam_count == 3:
            return "tres_cams_juego"
        return "spotlight"
    if cam_count == 1:
        return "vertical"
    if cam_count == 2:
        return "dividido"
    if cam_count == 3:
        return "trio"
    return "cuarteto"


def _row_rects(count: int, *, top: float, bottom: float) -> list[tuple[int, int, int, int]]:
    total_h = bottom - top
    step = total_h / count
    rects: list[tuple[int, int, int, int]] = []
    for index in range(count):
        y0 = int(round(top + step * index))
        y1 = int(round(top + step * (index + 1)))
        rects.append((0, y0 + (GAP if index else 0) // 2, CANVAS_W, y1 - y0 - GAP))
    return rects


def _band_rects(count: int, *, top: float, height: float) -> list[tuple[int, int, int, int]]:
    width = CANVAS_W / count
    rects: list[tuple[int, int, int, int]] = []
    for index in range(count):
        x0 = int(round(width * index))
        x1 = int(round(width * (index + 1)))
        rects.append((x0 + (GAP if index else 0) // 2, top, x1 - x0 - GAP, height))
    return rects


def _grid_rects(count: int, *, top: float, bottom: float) -> list[tuple[int, int, int, int]]:
    cols = 2
    rows = 2 if count == 4 else 1
    cell_w = CANVAS_W / cols
    cell_h = (bottom - top) / rows
    rects: list[tuple[int, int, int, int]] = []
    for index in range(count):
        col = index % cols
        row = index // cols
        rects.append(
            (
                int(round(cell_w * col)) + (GAP // 2 if col else 0),
                int(round(top + cell_h * row)) + (GAP // 2 if row else 0),
                int(round(cell_w)) - GAP,
                int(round(cell_h)) - GAP,
            )
        )
    return rects


def _cam_slots(
    rects: list[tuple[int, int, int, int]],
    cams: list[tuple[float, float, float, float]],
    *,
    pad: bool = False,
) -> list[Slot]:
    slots: list[Slot] = []
    for index, rect in enumerate(rects):
        box = cams[index] if index < len(cams) else None
        slots.append(Slot("cam" if box else "game", rect, box, pad=pad))
    return slots


def build_plan(
    template: str,
    cams: list[tuple[float, float, float, float]],
    *,
    canvas_w: int = CANVAS_W,
    canvas_h: int = CANVAS_H,
) -> LayoutPlan:
    """Return the slot geometry for ``template``.

    ``cams`` are facecam panels in source-frame pixels, ordered left to right
    then top to bottom. Missing panels degrade to the scene crop instead of
    leaving a hole.
    """
    name = normalize_template(template)
    if name == "auto":
        name = "vertical" if not cams else "cam_juego"
    cams = list(cams or [])

    if name == "vertical":
        return LayoutPlan(name, [Slot("game", (0, 0, canvas_w, canvas_h))], _anchor_for(name))
    if name == "centrado":
        return LayoutPlan(name, [Slot("full_blur", (0, 0, canvas_w, canvas_h))], _anchor_for(name))
    if name == "horizontal":
        return LayoutPlan(name, [Slot("full", (0, 0, canvas_w, canvas_h))], _anchor_for(name))
    if name == "spotlight":
        split = int(round(canvas_h * 0.62))
        slots = [
            Slot("game", (0, 0, canvas_w, split - GAP // 2)),
            Slot("full", (0, split + GAP // 2, canvas_w, canvas_h - split - GAP // 2)),
        ]
        return LayoutPlan(name, slots, _anchor_for(name, split))

    if name in {"dividido", "trio", "cuarteto"}:
        rects = _row_rects(2 if name == "dividido" else 3, top=0, bottom=canvas_h)
        if name == "cuarteto":
            rects = _grid_rects(4, top=0, bottom=canvas_h)
        return LayoutPlan(name, _cam_slots(rects, cams), _anchor_for(name))

    if name == "cam_juego":
        band = int(round(canvas_h * DEFAULT_CAM_BAND))
        slots = [
            Slot("cam", (0, 0, canvas_w, band - GAP // 2), cams[0] if cams else None, pad=True),
            Slot("game", (0, band + GAP // 2, canvas_w, canvas_h - band - GAP // 2)),
        ]
        return LayoutPlan(name, slots, _anchor_for(name, band))

    if name in {"dos_cams_juego", "tres_cams_juego"}:
        count = 2 if name == "dos_cams_juego" else 3
        band = int(round(canvas_h * (0.30 if count == 2 else 0.26)))
        slots = _cam_slots(_band_rects(count, top=0, height=band - GAP // 2), cams)
        slots.append(Slot("game", (0, band + GAP // 2, canvas_w, canvas_h - band - GAP // 2)))
        return LayoutPlan(name, slots, _anchor_for(name, band))

    if name == "trio_juego":
        band = int(round(canvas_h * 0.26))
        game_top = 0
        game_bottom = canvas_h - band - GAP // 2
        slots = [Slot("game", (0, game_top, canvas_w, game_bottom - game_top))]
        slots.extend(
            _cam_slots(
                _band_rects(3, top=game_bottom + GAP // 2, height=band - GAP // 2),
                cams,
            )
        )
        return LayoutPlan(name, slots, _anchor_for(name, None, game_bottom))

    # Unknown value: behave like the old vertical crop.
    return LayoutPlan("vertical", [Slot("game", (0, 0, canvas_w, canvas_h))], _anchor_for("vertical"))


def _anchor_for(template: str, band: int | None = None, game_bottom: int | None = None) -> int | None:
    """Y coordinate (canvas px) where subtitles must sit to avoid faces.

    ``None`` means the subtitle style default (bottom of the canvas) is fine.
    """
    if template in {"cam_juego", "dos_cams_juego", "tres_cams_juego"} and band:
        # Just below the camera row, over the gameplay panel.
        return min(CANVAS_H - 140, band + 150)
    if template == "trio_juego" and game_bottom:
        return max(220, game_bottom - 150)
    if template == "spotlight" and band:
        return max(220, band - 140)
    return None
