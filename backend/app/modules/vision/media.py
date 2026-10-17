"""Video and image processing of SAQ VISION: probing, frame extraction, frame quality, crops.

External processes run through `subprocess.run` with an argument list and a timeout, never through a shell.
"""

import io
import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageFilter, ImageOps

from app.config import get_settings

logger = logging.getLogger(__name__)

PROBE_TIMEOUT_S = 60
FFMPEG_TIMEOUT_S = 1200
# A video larger than this in either direction is not a camera recording we can sensibly decode.
MIN_SIDE_PX = 16
MAX_SIDE_PX = 8192

# Sharpness is the variance of the edge response on a grayscale copy downscaled to ANALYSIS_SIDE_PX.
# A flat or motion-blurred frame scores near zero, a detailed one well above 100.
ANALYSIS_SIDE_PX = 640
BLUR_THRESHOLD = 30.0
# dHash is 64 bits; frames whose hashes differ in at most this many bits are the same view.
DUPLICATE_HAMMING = 4
HASH_SIDE = 8

PREVIEW_MAX_SIDE = 640
PREVIEW_QUALITY = 85
CROP_QUALITY = 92
# Share of the box added on every side of a crop so letters touching the border are not cut.
CROP_PADDING = 0.05


class MediaError(Exception):
    """A video that cannot be processed; `code` is stored on the asset and job, `message` shown to people."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True)
class VideoInfo:
    width: int
    height: int
    duration_s: float | None


def _run(command: list[str], timeout: int, *, timeout_code: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(  # noqa: S603  (fixed binary, argument list, no shell)
            command, capture_output=True, text=True, timeout=timeout, check=False
        )
    except FileNotFoundError as exc:
        raise MediaError("ffmpeg_missing", "На сервере обработки нет ffmpeg") from exc
    except subprocess.TimeoutExpired as exc:
        raise MediaError(timeout_code, "Обработка видео заняла слишком много времени") from exc


def parse_probe(output: str) -> VideoInfo:
    """Validate `ffprobe -print_format json` output against the limits of the module."""
    try:
        data: dict[str, Any] = json.loads(output)
    except json.JSONDecodeError as exc:
        raise MediaError("video_undecodable", "Не удалось прочитать видеофайл") from exc
    streams = [
        stream
        for stream in data.get("streams", [])
        if stream.get("codec_type") == "video" and not stream.get("disposition", {}).get("attached_pic")
    ]
    if not streams:
        raise MediaError("video_no_stream", "В файле нет видеодорожки")
    stream = streams[0]
    width, height = int(stream.get("width") or 0), int(stream.get("height") or 0)
    if not (MIN_SIDE_PX <= width <= MAX_SIDE_PX and MIN_SIDE_PX <= height <= MAX_SIDE_PX):
        raise MediaError("video_bad_dimensions", f"Недопустимое разрешение видео: {width}x{height}")
    duration_s: float | None = None
    for raw in (data.get("format", {}).get("duration"), stream.get("duration")):
        try:
            duration_s = float(raw)
            break
        except (TypeError, ValueError):
            continue
    if duration_s is not None and duration_s > get_settings().vision_max_duration_seconds:
        raise MediaError(
            "video_too_long",
            f"Видео длиннее {get_settings().vision_max_duration_seconds // 60} мин, загрузите его частями",
        )
    return VideoInfo(width=width, height=height, duration_s=duration_s)


def probe_video(path: Path) -> VideoInfo:
    command = ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)]
    result = _run(command, PROBE_TIMEOUT_S, timeout_code="video_processing_timeout")
    if result.returncode != 0:
        logger.warning("ffprobe failed: %s", result.stderr[-500:])
        raise MediaError("video_undecodable", "Не удалось прочитать видеофайл")
    return parse_probe(result.stdout)


def frame_interval_s(duration_s: float | None) -> float:
    """Seconds between frames: the configured step, stretched so the whole video fits into `vision_max_frames`."""
    settings = get_settings()
    interval = settings.vision_frame_interval_seconds
    if duration_s is not None:
        interval = max(interval, duration_s / settings.vision_max_frames)
    return interval


def extract_frames(path: Path, out_dir: Path, interval_s: float) -> list[Path]:
    """One JPEG per `interval_s` at the original resolution (ffmpeg applies the rotation metadata itself)."""
    settings = get_settings()
    command = [
        "ffmpeg", "-nostdin", "-v", "error",
        "-t", str(settings.vision_max_duration_seconds),
        "-i", str(path),
        "-map", "0:v:0", "-an", "-sn",
        "-vf", f"fps={1 / interval_s:.6f}",
        "-frames:v", str(settings.vision_max_frames),
        "-q:v", "2",
        str(out_dir / "frame_%05d.jpg"),
    ]  # fmt: skip
    result = _run(command, FFMPEG_TIMEOUT_S, timeout_code="video_processing_timeout")
    frames = sorted(out_dir.glob("frame_*.jpg"))
    if result.returncode != 0 and not frames:
        logger.warning("ffmpeg failed: %s", result.stderr[-500:])
        raise MediaError("video_undecodable", "Не удалось декодировать видео")
    if not frames:
        raise MediaError("video_undecodable", "Из видео не получилось извлечь ни одного кадра")
    return frames


def _analysis_copy(image: Image.Image) -> Image.Image:
    gray = image.convert("L")
    gray.thumbnail((ANALYSIS_SIDE_PX, ANALYSIS_SIDE_PX))
    return gray


def sharpness(image: Image.Image) -> float:
    """Variance of the edge response: low for blurred or featureless frames."""
    gray = _analysis_copy(image)
    # PIL leaves the outermost pixels of a filtered image unfiltered; they are not an edge response.
    edges = gray.filter(ImageFilter.FIND_EDGES).crop((1, 1, gray.width - 1, gray.height - 1))
    histogram = edges.histogram()
    count = sum(histogram)
    mean = sum(level * n for level, n in enumerate(histogram)) / count
    return sum(n * (level - mean) ** 2 for level, n in enumerate(histogram)) / count


def dhash(image: Image.Image) -> int:
    """Difference hash: one bit per pixel of a 9x8 grayscale copy, set when it is brighter than its right neighbour."""
    small = image.convert("L").resize((HASH_SIDE + 1, HASH_SIDE), Image.Resampling.BILINEAR)
    pixels = list(small.tobytes())
    bits = 0
    for row in range(HASH_SIDE):
        for col in range(HASH_SIDE):
            bits = (bits << 1) | (pixels[row * (HASH_SIDE + 1) + col] > pixels[row * (HASH_SIDE + 1) + col + 1])
    return bits


def is_duplicate(hash_a: int, hash_b: int) -> bool:
    return (hash_a ^ hash_b).bit_count() <= DUPLICATE_HAMMING


def is_sharp(score: float) -> bool:
    return score >= BLUR_THRESHOLD


def make_preview(image: Image.Image) -> bytes:
    preview = image.convert("RGB")
    preview.thumbnail((PREVIEW_MAX_SIDE, PREVIEW_MAX_SIDE))
    buffer = io.BytesIO()
    preview.save(buffer, "JPEG", quality=PREVIEW_QUALITY)
    return buffer.getvalue()


def crop_region(data: bytes, bbox: dict[str, float]) -> bytes:
    """JPEG of the marked area cut from the original frame.

    `bbox` is in fractions of the picture as people see it, so the EXIF orientation is applied first (a photo is
    stored as uploaded, a video frame is already upright and has no orientation to apply).
    """
    with Image.open(io.BytesIO(data)) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
    pad_x, pad_y = bbox["w"] * CROP_PADDING, bbox["h"] * CROP_PADDING
    left = max(0, round((bbox["x"] - pad_x) * image.width))
    top = max(0, round((bbox["y"] - pad_y) * image.height))
    right = min(image.width, round((bbox["x"] + bbox["w"] + pad_x) * image.width))
    bottom = min(image.height, round((bbox["y"] + bbox["h"] + pad_y) * image.height))
    # A box thinner than a pixel still yields a valid (1 px) crop.
    right, bottom = max(right, left + 1), max(bottom, top + 1)
    buffer = io.BytesIO()
    image.crop((left, top, right, bottom)).save(buffer, "JPEG", quality=CROP_QUALITY)
    return buffer.getvalue()
