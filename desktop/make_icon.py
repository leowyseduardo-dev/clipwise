from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
ASSETS = HERE / "assets"
ASSETS.mkdir(parents=True, exist_ok=True)


def _lerp(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))  # type: ignore[return-value]


def build() -> Path:
    size = 256
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Blue rounded square with the same vertical gradient as the web logo.
    for y in range(8, 248):
        t = (y - 8) / 240
        color = _lerp((37, 99, 235), (29, 78, 216), t)
        draw.line((8, y, 248, y), fill=(*color, 255))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((8, 8, 248, 248), radius=62, fill=255)
    base = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    base.paste(image, (0, 0), mask)
    image = base
    draw = ImageDraw.Draw(image)

    # Play mark.
    draw.polygon([(102, 74), (102, 182), (190, 128)], fill=(255, 255, 255, 255))

    # Dark status dot, top-right, like LogoMark.
    draw.ellipse((176, 24, 232, 80), fill=(255, 255, 255, 255))
    draw.ellipse((184, 32, 224, 72), fill=(15, 23, 42, 255))

    out = ASSETS / "Clipwise.ico"
    image.save(
        out,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    png = ASSETS / "Clipwise.png"
    image.save(png, format="PNG")
    print(out)
    return out


if __name__ == "__main__":
    build()
