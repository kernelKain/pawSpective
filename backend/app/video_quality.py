from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


class VideoQualityError(RuntimeError):
    pass


@dataclass(frozen=True)
class VideoQualityAssessment:
    average_luma: float
    warnings: list[str]


def assess_video_quality(
    video_path: Path,
    sample_count: int = 8,
) -> VideoQualityAssessment:
    capture = cv2.VideoCapture(str(video_path))

    if not capture.isOpened():
        raise VideoQualityError("The video could not be inspected for quality.")

    try:
        frame_count = max(1, int(capture.get(cv2.CAP_PROP_FRAME_COUNT)))
        positions = np.linspace(0, frame_count - 1, sample_count, dtype=int)
        luma_samples: list[float] = []

        for position in positions:
            capture.set(cv2.CAP_PROP_POS_FRAMES, int(position))
            ok, frame = capture.read()

            if not ok or frame is None:
                continue

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            luma_samples.append(float(gray.mean()) / 255.0)

        if not luma_samples:
            raise VideoQualityError(
                "The video had no readable frames for quality inspection."
            )

        average_luma = float(np.mean(luma_samples))
        warnings: list[str] = []

        if average_luma < 0.12:
            warnings.append(
                "This footage is very dark, so object detection and color comparisons may be less reliable."
            )

        return VideoQualityAssessment(
            average_luma=average_luma,
            warnings=warnings,
        )
    finally:
        capture.release()
