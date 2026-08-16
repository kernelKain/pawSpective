from pathlib import Path

import cv2
import numpy as np

from backend.app.video_quality import assess_video_quality


def write_video(path: Path, value: int) -> None:
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        8,
        (64, 48),
    )
    assert writer.isOpened()
    try:
        frame = np.full((48, 64, 3), value, dtype=np.uint8)
        for _ in range(12):
            writer.write(frame)
    finally:
        writer.release()


def test_dark_footage_warns_without_being_rejected(tmp_path: Path) -> None:
    video = tmp_path / "dark.mp4"
    write_video(video, 10)
    result = assess_video_quality(video)
    assert result.average_luma < 0.12
    assert result.warnings


def test_bright_footage_has_no_darkness_warning(tmp_path: Path) -> None:
    video = tmp_path / "bright.mp4"
    write_video(video, 180)
    result = assess_video_quality(video)
    assert result.average_luma > 0.12
    assert result.warnings == []
