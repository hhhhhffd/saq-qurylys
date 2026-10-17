"""Object detector of SAQ VISION: Grounding DINO (open vocabulary, Apache-2.0) in the `vision-worker` image.

The model is pretrained and not fine-tuned on construction sites: its output is a hint for a person (plan, 4.1), never
a verdict. torch and transformers exist only in the `vision` images, so they are imported inside
`GroundingDinoDetector`; the API and the other workers never import them.
"""

import logging
import threading
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

from PIL import Image

from app.config import get_settings
from app.models.enums import VisionCategory

logger = logging.getLogger(__name__)

# Text prompts of the detector and the category each phrase stands for. Tuned on the frames described in
# docs/SAQ_VISION_EVAL.md; changing a phrase changes what is found, so the prompts are stored with every run.
CATEGORY_PROMPTS: dict[VisionCategory, tuple[str, ...]] = {
    VisionCategory.outdoor_ad: ("billboard", "advertising banner"),
    VisionCategory.fence: ("construction fence", "fence"),
    VisionCategory.site_gate: ("gate",),
    VisionCategory.waste_container: ("dumpster", "skip container", "waste container"),
    VisionCategory.wheel_wash: ("wheel washing station",),
    VisionCategory.debris: ("pile of construction debris", "garbage pile", "scattered trash"),
}
# Detected objects with these categories are only observed; debris is something a person must look at.
POSSIBLE_NONCOMPLIANCE = frozenset({VisionCategory.debris})
PHRASE_CATEGORY = {phrase: category for category, phrases in CATEGORY_PROMPTS.items() for phrase in phrases}
# Boxes of the same object on adjacent frames overlap at least this much (fractions of the frame).
GROUP_IOU = 0.3
# Boxes of one category on one frame overlapping this much are one detection (several phrases fire on one object).
DUPLICATE_IOU = 0.7
MODEL_NAME_MAX = 40


class DetectorUnavailable(Exception):
    """The model cannot be loaded here (no torch, no weights, no device); the run fails with `detector_unavailable`."""


@dataclass(frozen=True)
class Box:
    """A rectangle in fractions of the frame, origin at the top-left corner."""

    x: float
    y: float
    w: float
    h: float

    def as_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass(frozen=True)
class Detection:
    category: VisionCategory
    label: str  # the phrase of the prompt that matched
    box: Box
    confidence: float


class Detector(Protocol):
    model_version: str
    device: str
    precision: str

    def detect(self, images: Sequence[Image.Image]) -> list[list[Detection]]:
        """Detections of every image, in order. Boxes are fractions of the image they were found on."""
        ...


def prompt_text() -> str:
    """Grounding DINO takes lower-case phrases separated by full stops."""
    return " ".join(f"{phrase}." for phrase in PHRASE_CATEGORY)


def match_label(label: str) -> tuple[VisionCategory, str] | None:
    """The category and prompt phrase for a text label of the model, or None when it is not one of ours.

    The model returns the tokens it attached the box to: usually a whole phrase, sometimes a part of one ("skip") or
    two phrases glued together. An exact phrase wins; otherwise a phrase contained in the label or containing it; a
    label that fits phrases of different categories is dropped rather than guessed.
    """
    label = label.strip().lower()
    if not label:
        return None
    if label in PHRASE_CATEGORY:
        return PHRASE_CATEGORY[label], label
    fitting = [phrase for phrase in PHRASE_CATEGORY if phrase in label or set(label.split()) <= set(phrase.split())]
    categories = {PHRASE_CATEGORY[phrase] for phrase in fitting}
    if len(categories) != 1:
        return None
    # Prefer the longest phrase so that "fence" does not win over "construction fence" for a label naming both.
    return categories.pop(), max(fitting, key=len)


def iou(a: Box, b: Box) -> float:
    width = min(a.x + a.w, b.x + b.w) - max(a.x, b.x)
    height = min(a.y + a.h, b.y + b.h) - max(a.y, b.y)
    if width <= 0 or height <= 0:
        return 0.0
    inter = width * height
    return inter / (a.w * a.h + b.w * b.h - inter)


def box_from_corners(x0: float, y0: float, x1: float, y1: float) -> Box | None:
    """A box given by corners in fractions, clipped to the frame; None when nothing of it is left."""
    x0, y0, x1, y1 = (min(max(value, 0.0), 1.0) for value in (x0, y0, x1, y1))
    if x1 - x0 < 1e-4 or y1 - y0 < 1e-4:
        return None
    return Box(x=x0, y=y0, w=x1 - x0, h=y1 - y0)


def drop_duplicates(detections: list[Detection]) -> list[Detection]:
    """Per category, a box nearly coinciding with a more confident one is the same object under another phrase."""
    kept: list[Detection] = []
    for item in sorted(detections, key=lambda d: d.confidence, reverse=True):
        if not any(k.category is item.category and iou(k.box, item.box) >= DUPLICATE_IOU for k in kept):
            kept.append(item)
    return kept


def assign_groups(frames: Sequence[Sequence[Detection]], first_key: int = 1) -> list[list[int]]:
    """Group keys of the detections of consecutive frames of one video, so one object is counted once.

    A detection joins the group of a detection of the same category on the previous frame when their boxes overlap
    (IoU >= GROUP_IOU); the best overlaps are matched first and each box is matched at most once. Everything else
    starts a new group. Keys increase from `first_key`. A photo is a one-frame sequence: every box is its own group.
    """
    keys: list[list[int]] = []
    next_key = first_key
    previous: Sequence[Detection] = []
    previous_keys: list[int] = []
    for detections in frames:
        pairs = sorted(
            (
                (overlap, i, j)
                for i, current in enumerate(detections)
                for j, before in enumerate(previous)
                if current.category is before.category and (overlap := iou(current.box, before.box)) >= GROUP_IOU
            ),
            reverse=True,
        )
        assigned: dict[int, int] = {}
        used: set[int] = set()
        for _, i, j in pairs:
            if i not in assigned and j not in used:
                assigned[i] = previous_keys[j]
                used.add(j)
        frame_keys = []
        for i in range(len(detections)):
            if i not in assigned:
                assigned[i] = next_key
                next_key += 1
            frame_keys.append(assigned[i])
        keys.append(frame_keys)
        previous, previous_keys = detections, frame_keys
    return keys


def _revision(model_id: str) -> str:
    """The commit of the model repository the cached weights belong to (the snapshot directory is named after it)."""
    from huggingface_hub import try_to_load_from_cache

    cached = try_to_load_from_cache(model_id, "config.json")
    return Path(cached).parent.name if isinstance(cached, str) else "unknown"


class GroundingDinoDetector:
    def __init__(
        self, model_id: str, device: str, box_threshold: float, text_threshold: float, max_side: int, half: bool = True
    ) -> None:
        try:
            import torch
            from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor
        except ImportError as exc:
            raise DetectorUnavailable("torch and transformers are not installed in this image") from exc
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        elif device == "cuda" and not torch.cuda.is_available():
            raise DetectorUnavailable("VISION_DETECTOR_DEVICE=cuda but no GPU is visible to the container")
        self._torch = torch
        self.device = device
        self.box_threshold, self.text_threshold, self.max_side = box_threshold, text_threshold, max_side
        try:
            self._processor = AutoProcessor.from_pretrained(model_id)
            model = AutoModelForZeroShotObjectDetection.from_pretrained(model_id)
        except OSError as exc:  # weights absent from the cache (the image is offline at run time)
            raise DetectorUnavailable(f"weights of {model_id} are not available: {exc}") from exc
        # fp16 on a GPU: 1.8x faster and half the memory, boxes agree with fp32 (IoU 0.99; only borderline-threshold
        # detections differ), see docs/SAQ_VISION_EVAL.md. The CPU always uses fp32.
        self._half = half and device == "cuda"
        self.precision = "fp16" if self._half else "fp32"
        self._model = (model.half() if self._half else model).to(device).eval()
        self.model_version = f"{model_id.rsplit('/', 1)[-1][:MODEL_NAME_MAX]}@{_revision(model_id)[:12]}"
        self._text = prompt_text()
        logger.info("Detector %s loaded on %s", self.model_version, self.device)

    def detect(self, images: Sequence[Image.Image]) -> list[list[Detection]]:
        results: list[list[Detection]] = [[] for _ in images]
        # Images of one size go through the model together: padding would shift the relative boxes.
        by_size: dict[tuple[int, int], list[int]] = {}
        for index, image in enumerate(images):
            by_size.setdefault(image.size, []).append(index)
        for indexes in by_size.values():
            for position, found in zip(indexes, self._run([images[i] for i in indexes]), strict=True):
                results[position] = found
        return results

    def _run(self, images: list[Image.Image]) -> list[list[Detection]]:
        torch = self._torch
        # `size` makes the processor produce at most max_side pixels on the longer side (its default is 800/1333).
        inputs = self._processor(
            images=images,
            text=[self._text] * len(images),
            return_tensors="pt",
            size={"shortest_edge": self.max_side, "longest_edge": self.max_side},
        ).to(self.device)
        with torch.inference_mode():
            if self._half:
                inputs["pixel_values"] = inputs["pixel_values"].half()
            outputs = self._model(**inputs)
            outputs.logits, outputs.pred_boxes = outputs.logits.float(), outputs.pred_boxes.float()
        processed = self._processor.post_process_grounded_object_detection(
            outputs,
            inputs.input_ids,
            threshold=self.box_threshold,
            text_threshold=self.text_threshold,
            target_sizes=[(1, 1)] * len(images),  # boxes come back as fractions
        )
        return [self._detections(item) for item in processed]

    def _detections(self, item: Any) -> list[Detection]:
        found: list[Detection] = []
        if len(item["scores"]) == 0:
            return found  # with no boxes the processor still answers with one empty label
        for score, corners, label in zip(item["scores"], item["boxes"], item["text_labels"], strict=True):
            matched = match_label(label)
            box = box_from_corners(*(float(value) for value in corners))
            if matched is not None and box is not None:
                found.append(Detection(category=matched[0], label=matched[1], box=box, confidence=float(score)))
        return drop_duplicates(found)


_detector: Detector | None = None
_lock = threading.Lock()


def get_detector() -> Detector:
    """The detector of this process, loaded on first use (loading takes seconds and a few hundred MB)."""
    global _detector
    with _lock:
        if _detector is None:
            settings = get_settings()
            if settings.vision_detector_backend != "grounding_dino":
                raise DetectorUnavailable("the detector is disabled")
            _detector = GroundingDinoDetector(
                settings.vision_detector_model,
                settings.vision_detector_device,
                settings.vision_detector_box_threshold,
                settings.vision_detector_text_threshold,
                settings.vision_detector_max_side,
            )
        return _detector
