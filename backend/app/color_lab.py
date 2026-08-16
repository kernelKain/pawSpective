from pathlib import Path

import cv2
import numpy as np

from backend.app.contracts import (
    ColorSimulationOption,
    ColorSimulationResponse,
    SceneEvent,
    ToyColorId,
)
from backend.app.visibility import (
    VisibilityScoringError,
    canine_approximation,
    relative_contrast_score,
    rgb_to_hex,
    sample_event_median_colors,
)


PALETTE: tuple[tuple[ToyColorId, str, str], ...] = (
    ("blue", "Bright blue", "#2F6BFF"),
    ("yellow", "Bright yellow", "#FFD43B"),
    ("red", "Bright red", "#E63946"),
    ("green", "Grass green", "#43AA4B"),
    ("orange", "Bright orange", "#FF8A2B"),
    ("purple", "Bright purple", "#8B5CF6"),
)

DISCLAIMER = (
    "Screen-color simulation using a fixed palette and the measured "
    "nearby background. It is not exact canine vision, object "
    "segmentation, or a physical-product guarantee."
)


class ColorSimulationError(ValueError):
    pass


def hex_to_rgb(value: str) -> np.ndarray:
    normalized = value.removeprefix("#")

    if len(normalized) != 6:
        raise ValueError("Expected a six-digit hexadecimal color")

    try:
        channels = [
            int(normalized[0:2], 16),
            int(normalized[2:4], 16),
            int(normalized[4:6], 16),
        ]
    except ValueError as error:
        raise ValueError("Expected a six-digit hexadecimal color") from error

    return np.array(channels, dtype=np.float32) / 255.0


def explain_candidate(label: str, dog_contrast: int, gain: int) -> str:
    if dog_contrast >= 67:
        visibility = (
            f"{label} has strong simulated separation from "
            "the measured nearby background."
        )
    elif dog_contrast >= 34:
        visibility = (
            f"{label} has moderate simulated separation from "
            "the measured nearby background."
        )
    else:
        visibility = (
            f"{label} has low simulated separation and may "
            "blend with the measured nearby background."
        )

    if gain >= 10:
        comparison = " It scores higher than the object's sampled original color."
    elif gain <= -10:
        comparison = " It scores lower than the object's sampled original color."
    else:
        comparison = " It scores similarly to the object's sampled original color."

    return visibility + comparison


def simulate_event_frame(
    frame_rgb: np.ndarray,
    event: SceneEvent,
) -> ColorSimulationResponse:
    try:
        human_object, human_background = sample_event_median_colors(
            frame_rgb,
            event,
        )
    except VisibilityScoringError as error:
        raise ColorSimulationError(str(error)) from error

    dog_object = canine_approximation(human_object[np.newaxis, :])[0]
    dog_background = canine_approximation(human_background[np.newaxis, :])[0]
    original_human_contrast = relative_contrast_score(
        human_object,
        human_background,
    )
    original_dog_contrast = relative_contrast_score(
        dog_object,
        dog_background,
    )

    unranked: list[dict[str, object]] = []

    for color_id, label, color_hex in PALETTE:
        human_candidate = hex_to_rgb(color_hex)
        dog_candidate = canine_approximation(human_candidate[np.newaxis, :])[0]
        human_contrast = relative_contrast_score(
            human_candidate,
            human_background,
        )
        dog_contrast = relative_contrast_score(
            dog_candidate,
            dog_background,
        )
        gain = dog_contrast - original_dog_contrast

        unranked.append(
            {
                "color_id": color_id,
                "label": label,
                "human_color": rgb_to_hex(human_candidate),
                "dog_approx_color": rgb_to_hex(dog_candidate),
                "human_contrast_score": human_contrast,
                "dog_contrast_score": dog_contrast,
                "dog_contrast_gain": gain,
                "contrast_change": dog_contrast - human_contrast,
                "explanation": explain_candidate(label, dog_contrast, gain),
            }
        )

    ranked = sorted(
        unranked,
        key=lambda option: (
            -int(option["dog_contrast_score"]),
            str(option["color_id"]),
        ),
    )
    options = [
        ColorSimulationOption(**option, rank=index + 1)
        for index, option in enumerate(ranked)
    ]

    return ColorSimulationResponse(
        simulation_version="1.0",
        method="fixed-swatch-background-lab-v1",
        event_id=event.event_id,
        original_human_color=rgb_to_hex(human_object),
        original_dog_color=rgb_to_hex(dog_object),
        human_background_color=rgb_to_hex(human_background),
        dog_background_color=rgb_to_hex(dog_background),
        original_human_contrast_score=original_human_contrast,
        original_dog_contrast_score=original_dog_contrast,
        recommended_color_id=options[0].color_id,
        options=options,
        disclaimer=DISCLAIMER,
    )


def simulate_object_colors(
    video_path: Path,
    event: SceneEvent,
    duration_ms: int,
) -> ColorSimulationResponse:
    if event.timestamp_ms > duration_ms:
        raise ColorSimulationError(
            "The selected event timestamp exceeds the video duration."
        )

    capture = cv2.VideoCapture(str(video_path))

    if not capture.isOpened():
        raise ColorSimulationError("The normalized video could not be opened.")

    try:
        capture.set(cv2.CAP_PROP_POS_MSEC, event.timestamp_ms)
        readable, frame_bgr = capture.read()

        if not readable or frame_bgr is None:
            raise ColorSimulationError(
                "The selected event frame could not be read."
            )

        frame_rgb = (
            cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB).astype(np.float32)
            / 255.0
        )
        return simulate_event_frame(frame_rgb, event)
    finally:
        capture.release()
