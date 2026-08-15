import math
import re
from pathlib import Path

import cv2
import numpy as np

from backend.app.contracts import (
    MotionLevel,
    ObjectCategory,
    SalienceLevel,
    SceneEvent,
    VisibilityAnalysisResponse,
    VisibilityScore,
)


CANINE_MATRIX = np.array(
    [
        [0.367322, 0.860646, -0.227968],
        [0.280085, 0.672501, 0.047413],
        [-0.011820, 0.042940, 0.968881],
    ],
    dtype=np.float32,
)

MOTION_SCORES = {
    MotionLevel.NONE: 0,
    MotionLevel.LOW: 33,
    MotionLevel.MEDIUM: 67,
    MotionLevel.HIGH: 100,
}

MAXIMUM_SAMPLED_PIXELS = 50_000
MINIMUM_REGION_PIXELS = 25
DELTA_E_FULL_SCALE = 80.0


class VisibilityScoringError(ValueError):
    pass


def canine_approximation(rgb: np.ndarray) -> np.ndarray:
    """
    Apply the same engineering approximation used by the WebGL Dog Lens.

    Input and output values are sRGB floats from 0.0 to 1.0. This is a
    display approximation, not a reconstruction of exact canine vision.
    """
    source = np.clip(rgb.astype(np.float32), 0.0, 1.0)
    linear = np.power(source, 2.2)
    transformed = linear @ CANINE_MATRIX.T
    transformed = np.clip(transformed, 0.0, 1.0)

    return np.power(transformed, 1.0 / 2.2)


def _sample_pixels(pixels: np.ndarray) -> np.ndarray:
    if len(pixels) <= MAXIMUM_SAMPLED_PIXELS:
        return pixels

    stride = math.ceil(len(pixels) / MAXIMUM_SAMPLED_PIXELS)
    return pixels[::stride]


def _extract_regions(
    frame_rgb: np.ndarray,
    event: SceneEvent,
) -> tuple[np.ndarray, np.ndarray]:
    height, width, _ = frame_rgb.shape
    box = event.bounding_box

    x0 = max(0, min(width - 1, math.floor(box.x_min * width)))
    y0 = max(0, min(height - 1, math.floor(box.y_min * height)))
    x1 = max(x0 + 1, min(width, math.ceil(box.x_max * width)))
    y1 = max(y0 + 1, min(height, math.ceil(box.y_max * height)))

    box_width = x1 - x0
    box_height = y1 - y0

    inset_x = min(
        max(0, round(box_width * 0.12)),
        max(0, (box_width - 1) // 2),
    )
    inset_y = min(
        max(0, round(box_height * 0.12)),
        max(0, (box_height - 1) // 2),
    )

    inner_x0 = x0 + inset_x
    inner_y0 = y0 + inset_y
    inner_x1 = x1 - inset_x
    inner_y1 = y1 - inset_y

    object_mask = np.zeros((height, width), dtype=bool)
    object_mask[inner_y0:inner_y1, inner_x0:inner_x1] = True

    expand_x = max(3, round(box_width * 0.40))
    expand_y = max(3, round(box_height * 0.40))

    outer_x0 = max(0, x0 - expand_x)
    outer_y0 = max(0, y0 - expand_y)
    outer_x1 = min(width, x1 + expand_x)
    outer_y1 = min(height, y1 + expand_y)

    background_mask = np.zeros((height, width), dtype=bool)
    background_mask[outer_y0:outer_y1, outer_x0:outer_x1] = True
    background_mask[y0:y1, x0:x1] = False

    object_pixels = frame_rgb[object_mask]
    background_pixels = frame_rgb[background_mask]

    if len(object_pixels) < MINIMUM_REGION_PIXELS:
        raise VisibilityScoringError(
            f"{event.event_id}: object region is too small to score.",
        )

    if len(background_pixels) < MINIMUM_REGION_PIXELS:
        raise VisibilityScoringError(
            f"{event.event_id}: surrounding background is too small to score.",
        )

    return (
        _sample_pixels(object_pixels),
        _sample_pixels(background_pixels),
    )


def _median_color(pixels: np.ndarray) -> np.ndarray:
    return np.median(pixels, axis=0).astype(np.float32)


def _lab_delta(left_rgb: np.ndarray, right_rgb: np.ndarray) -> float:
    pair = np.array([[left_rgb, right_rgb]], dtype=np.float32)
    lab_pair = cv2.cvtColor(pair, cv2.COLOR_RGB2LAB)[0]

    return float(np.linalg.norm(lab_pair[0] - lab_pair[1]))


def _contrast_score(
    object_color: np.ndarray,
    background_color: np.ndarray,
) -> int:
    delta_e = _lab_delta(object_color, background_color)
    normalized = min(1.0, max(0.0, delta_e / DELTA_E_FULL_SCALE))

    return round(normalized * 100)


def _hex_color(rgb: np.ndarray) -> str:
    channels = np.rint(np.clip(rgb, 0.0, 1.0) * 255).astype(int)

    return "#{:02X}{:02X}{:02X}".format(*channels)


def _favorite_matches(event: SceneEvent, favorite: str) -> bool:
    normalized_favorite = favorite.strip().lower()
    words = set(re.findall(r"[a-z]+", event.object_label.lower()))

    if normalized_favorite == "ball":
        return "ball" in words

    if normalized_favorite == "food":
        return event.category == ObjectCategory.FOOD

    if normalized_favorite == "people":
        return event.category == ObjectCategory.PERSON

    if normalized_favorite == "dogs":
        return bool(words & {"dog", "dogs", "puppy", "puppies"})

    if normalized_favorite == "cats":
        return bool(words & {"cat", "cats", "kitten", "kittens"})

    if normalized_favorite == "squirrels":
        return bool(words & {"squirrel", "squirrels"})

    # "Sniffing" is not a visibly identifiable object and must not create a
    # science-mode bonus.
    return False


def _salience_level(score: int) -> SalienceLevel:
    if score >= 67:
        return SalienceLevel.HIGH

    if score >= 34:
        return SalienceLevel.MEDIUM

    return SalienceLevel.LOW


def score_event_frame(
    frame_rgb: np.ndarray,
    event: SceneEvent,
    favorite_interest: str,
) -> VisibilityScore:
    object_pixels, background_pixels = _extract_regions(
        frame_rgb,
        event,
    )

    human_object = _median_color(object_pixels)
    human_background = _median_color(background_pixels)

    dog_object_pixels = canine_approximation(object_pixels)
    dog_background_pixels = canine_approximation(background_pixels)

    dog_object = _median_color(dog_object_pixels)
    dog_background = _median_color(dog_background_pixels)

    human_contrast = _contrast_score(
        human_object,
        human_background,
    )
    dog_contrast = _contrast_score(
        dog_object,
        dog_background,
    )

    motion_score = MOTION_SCORES[event.motion_level]

    box = event.bounding_box
    normalized_area = (
        (box.x_max - box.x_min)
        * (box.y_max - box.y_min)
    )

    # A box occupying 25% of the frame reaches the top apparent-size score.
    apparent_size_score = round(
        min(1.0, math.sqrt(normalized_area) / 0.5) * 100,
    )

    profile_relevance_score = (
        100 if _favorite_matches(event, favorite_interest) else 0
    )

    # Profile relevance contributes at most ten points.
    salience_score = round(
        0.35 * motion_score
        + 0.35 * dog_contrast
        + 0.20 * apparent_size_score
        + 0.10 * profile_relevance_score
    )

    contrast_change = dog_contrast - human_contrast

    if contrast_change <= -10:
        explanation = (
            "The object loses separation from its nearby background "
            "after the canine-vision approximation."
        )
    elif contrast_change >= 10:
        explanation = (
            "The object remains more distinct from its nearby background "
            "after the canine-vision approximation."
        )
    else:
        explanation = (
            "The object has similar relative separation before and after "
            "the canine-vision approximation."
        )

    why: list[str] = []

    if motion_score >= 67:
        why.append("Visible motion increased the cue score.")

    if dog_contrast >= 67:
        why.append("The transformed object/background contrast is high.")
    elif dog_contrast <= 33:
        why.append("The transformed object/background contrast is low.")

    if apparent_size_score >= 60:
        why.append("The object occupies a prominent part of the frame.")

    if profile_relevance_score:
        why.append(
            "The profile favorite added a small Curiosity Mode bonus.",
        )

    if not why:
        why.append(
            "The cue is supported mainly by its visible location and size.",
        )

    return VisibilityScore(
        event_id=event.event_id,
        identification_confidence=event.confidence,
        human_contrast_score=human_contrast,
        dog_contrast_score=dog_contrast,
        contrast_change=contrast_change,
        motion_score=motion_score,
        apparent_size_score=apparent_size_score,
        profile_relevance_score=profile_relevance_score,
        salience_score=salience_score,
        salience_level=_salience_level(salience_score),
        human_object_color=_hex_color(human_object),
        human_background_color=_hex_color(human_background),
        dog_object_color=_hex_color(dog_object),
        dog_background_color=_hex_color(dog_background),
        explanation=explanation,
        why=why[:4],
    )


def score_visibility_events(
    video_path: Path,
    events: list[SceneEvent],
    favorite_interest: str,
    duration_ms: int,
) -> VisibilityAnalysisResponse:
    invalid_timestamps = [
        event.event_id
        for event in events
        if event.timestamp_ms > duration_ms
    ]

    if invalid_timestamps:
        raise VisibilityScoringError(
            "Event timestamps exceed the video duration: "
            + ", ".join(invalid_timestamps),
        )

    capture = cv2.VideoCapture(str(video_path))

    if not capture.isOpened():
        raise VisibilityScoringError(
            "The normalized video could not be opened for scoring.",
        )

    scores: list[VisibilityScore] = []
    warnings: list[str] = []

    try:
        for event in events:
            capture.set(cv2.CAP_PROP_POS_MSEC, event.timestamp_ms)
            readable, frame_bgr = capture.read()

            if not readable or frame_bgr is None:
                warnings.append(
                    f"{event.event_id}: its video frame could not be read.",
                )
                continue

            frame_rgb = (
                cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                .astype(np.float32)
                / 255.0
            )

            try:
                scores.append(
                    score_event_frame(
                        frame_rgb,
                        event,
                        favorite_interest,
                    ),
                )
            except VisibilityScoringError as error:
                warnings.append(str(error))

    finally:
        capture.release()

    if not scores:
        raise VisibilityScoringError(
            "No corrected event could be scored from this video.",
        )

    return VisibilityAnalysisResponse(
        scoring_version="1.0",
        method="bbox-region-lab-v1",
        scores=scores,
        warnings=warnings,
    )