"""Synthetic pictures for the demo data: stylized construction sites drawn with Pillow, no real footage.

The demo stores them as evidence, as frames of drone flights and as screenshots of publications. Everything here is
deterministic: the same arguments give the same picture. `python -m app.seed_media DIR NAME BANNER PROGRESS SECONDS FPS`
writes the frames of a flight for ffmpeg; `seed_data/demo_flight_*.mp4` were assembled that way:

    ffmpeg -framerate 12 -i DIR/frame_%05d.jpg -c:v libx264 -crf 30 -pix_fmt yuv420p -movflags +faststart out.mp4
"""

import io
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SIZE = (960, 540)
_FONT_FILES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
)

# Fractions of the frame: where each feature of the site stands at t=0; the camera drifts to the left.
_DRIFT_PX_PER_S = 8
_FEATURES = {
    "billboard": (700, 100, 220, 130),
    "fence": (80, 200, 560, 290),
    "gate": (90, 400, 70, 80),
    "container": (545, 425, 62, 36),
    "debris": (570, 458, 55, 24),
    "building": (200, 170, 220, 270),
}


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _FONT_FILES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def feature_bbox(feature: str, t: float = 0.0, size: tuple[int, int] = SIZE) -> dict[str, float]:
    """The box of a feature as fractions of the frame at the moment `t` (the camera drifts with time)."""
    x, y, w, h = _FEATURES[feature]
    left = x - t * _DRIFT_PX_PER_S
    return {
        "x": round(left / size[0], 4),
        "y": round(y / size[1], 4),
        "w": round(w / size[0], 4),
        "h": round(h / size[1], 4),
    }


def _wrap(
    draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont | ImageFont.ImageFont, width: int
) -> list[str]:
    lines: list[str] = []
    line = ""
    for word in text.split():
        candidate = f"{line} {word}".strip()
        if line and draw.textlength(candidate, font=font) > width:
            lines.append(line)
            line = word
        else:
            line = candidate
    return [*lines, line] if line else lines


def site_frame(t: float, name: str, banner: str, progress: float, *, view_shift: float = 0.0) -> Image.Image:
    """A stylized site seen from above at the moment `t` seconds: fence, gate, frame of the building with a crane,
    a container, a heap of debris and a billboard with the banner text."""
    image = Image.new("RGB", SIZE, (126, 156, 108))
    draw = ImageDraw.Draw(image)
    shift = -(t + view_shift) * _DRIFT_PX_PER_S

    def box(feature: str, grow: int = 0) -> tuple[float, float, float, float]:
        x, y, w, h = _FEATURES[feature]
        return (x + shift - grow, y - grow, x + shift + w + grow, y + h + grow)

    draw.rectangle((0, 470, SIZE[0], SIZE[1]), fill=(96, 98, 104))  # the road
    for x in range(-40, SIZE[0] + 40, 80):
        draw.rectangle((x + shift % 80, 500, x + shift % 80 + 40, 506), fill=(214, 214, 200))
    draw.rectangle(box("fence", 6), fill=(168, 150, 112))  # the ground of the site
    fence = box("fence")
    for x in range(int(fence[0]), int(fence[2]), 14):
        draw.rectangle((x, fence[1] - 8, x + 9, fence[1]), fill=(52, 98, 160))
        draw.rectangle((x, fence[3], x + 9, fence[3] + 8), fill=(52, 98, 160))
    draw.rectangle(fence, outline=(52, 98, 160), width=4)
    gate = box("gate")
    draw.rectangle(gate, fill=(168, 150, 112))
    draw.rectangle((gate[0] + 2, gate[1] - 6, gate[0] + 12, gate[3]), fill=(236, 190, 40))
    draw.rectangle((gate[2] - 12, gate[1] - 6, gate[2] - 2, gate[3]), fill=(236, 190, 40))

    left, top, right, bottom = box("building")
    floors = max(1, round(progress * 9))
    floor_h = (bottom - top) / 9
    for floor in range(floors):
        y1 = bottom - floor * floor_h
        draw.rectangle((left, y1 - floor_h + 3, right, y1), fill=(196, 196, 190), outline=(120, 120, 116))
        for x in range(int(left) + 14, int(right) - 14, 34):
            draw.rectangle((x, y1 - floor_h + 12, x + 16, y1 - 8), fill=(70, 96, 128))
    for column in (left, right):  # bare columns of the floors that are not built yet
        draw.line((column, bottom - floors * floor_h, column, top), fill=(150, 150, 146), width=2)

    mast_x = left + 150
    draw.line((mast_x, bottom, mast_x, top - 70), fill=(236, 190, 40), width=7)
    draw.line((mast_x - 150, top - 70, mast_x + 130, top - 70), fill=(236, 190, 40), width=6)
    trolley = mast_x + 60 + 50 * math.sin(t * 0.9)
    draw.line((trolley, top - 70, trolley, top + 10 + 12 * math.sin(t * 1.3)), fill=(60, 60, 60), width=2)
    draw.rectangle(
        (trolley - 8, top + 10 + 12 * math.sin(t * 1.3), trolley + 8, top + 24 + 12 * math.sin(t * 1.3)),
        fill=(214, 90, 40),
    )

    container = box("container")
    draw.rectangle(container, fill=(40, 120, 168), outline=(20, 70, 100), width=2)
    debris = box("debris")
    for index in range(7):
        base = debris[0] + index * 7
        draw.polygon(
            [(base, debris[3]), (base + 9, debris[1] + (index * 5) % 14), (base + 18, debris[3])],
            fill=(110 + index * 8, 108, 100),
        )

    sign = box("billboard")
    for pole in (sign[0] + 24, sign[2] - 24):
        draw.rectangle((pole - 4, sign[3], pole + 4, sign[3] + 60), fill=(70, 70, 74))
    draw.rectangle(sign, fill=(200, 30, 50), outline=(255, 255, 255), width=5)
    banner_font = _font(24)
    y = sign[1] + 12
    for line in _wrap(draw, banner, banner_font, int(sign[2] - sign[0]) - 24)[:3]:
        draw.text((sign[0] + 12, y), line, font=banner_font, fill=(255, 255, 255))
        y += 30
    small = _font(15)
    draw.text((sign[0] + 12, sign[3] - 26), name, font=small, fill=(255, 226, 150))
    return image


def to_jpeg(image: Image.Image, quality: int = 82) -> bytes:
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, "JPEG", quality=quality)
    return buffer.getvalue()


def post_screenshot(seed: int, accent: str | None = None) -> bytes:
    """A wireframe of a post in a feed (header, picture, lines of text): a stand-in for a page capture."""
    palette = [(52, 98, 160), (180, 70, 110), (60, 140, 110), (200, 130, 40), (110, 80, 170)]
    color = palette[seed % len(palette)]
    image = Image.new("RGB", (480, 320), (246, 246, 248))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 480, 44), fill=color)
    draw.ellipse((12, 8, 40, 36), fill=(255, 255, 255))
    draw.rectangle((52, 14, 52 + 80 + seed % 60, 24), fill=(255, 255, 255))
    draw.rectangle((16, 60, 464, 190), fill=tuple(min(255, c + 70) for c in color))
    draw.polygon([(16, 190), (130, 110), (210, 160), (290, 90), (464, 190)], fill=color)
    if accent:
        draw.text((24, 66), accent, font=_font(22), fill=(255, 255, 255))
    for row in range(4):
        width = 440 - ((seed * 37 + row * 91) % 160)
        draw.rectangle((16, 206 + row * 22, 16 + width, 216 + row * 22), fill=(205, 205, 210))
    buffer = io.BytesIO()
    image.quantize(48).save(buffer, "PNG", optimize=True)
    return buffer.getvalue()


def main(argv: list[str]) -> None:
    directory, name, banner, progress, seconds, fps = argv
    out = Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    for index in range(int(float(seconds) * int(fps))):
        site_frame(index / int(fps), name, banner, float(progress)).save(out / f"frame_{index:05d}.jpg", quality=80)


if __name__ == "__main__":
    main(sys.argv[1:])
