import asyncio
import shutil
import subprocess
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import UploadFile

import backend.app.media as media_module
from backend.app.media import (
    MediaValidationError,
    normalize_video,
    probe_duration_ms,
    save_upload,
)


def test_save_upload_closes_file_and_uses_configured_limit(
    tmp_path: Path,
) -> None:
    source = BytesIO(b"x" * (1024 * 1024 + 1))
    upload = UploadFile(file=source, filename="clip.mp4")
    destination = tmp_path / "clip.mp4"

    with pytest.raises(MediaValidationError, match="1 MB"):
        asyncio.run(save_upload(upload, destination, 1024 * 1024))

    assert source.closed
    assert not destination.exists()


def test_save_upload_rejects_empty_video(tmp_path: Path) -> None:
    source = BytesIO()
    upload = UploadFile(file=source, filename="clip.mp4")
    destination = tmp_path / "clip.mp4"

    with pytest.raises(MediaValidationError, match="empty"):
        asyncio.run(save_upload(upload, destination, 1024))

    assert source.closed
    assert not destination.exists()


@pytest.mark.parametrize("duration", ["NaN", "Infinity", "0", "-1"])
def test_probe_rejects_non_finite_or_non_positive_duration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    duration: str,
) -> None:
    monkeypatch.setattr(media_module.shutil, "which", lambda _: "ffprobe")
    monkeypatch.setattr(
        media_module.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout=f'{{"format": {{"duration": "{duration}"}}}}',
        ),
    )

    with pytest.raises(MediaValidationError, match="could not be determined"):
        probe_duration_ms(tmp_path / "clip.mp4")


def test_probe_translates_timeout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(media_module.shutil, "which", lambda _: "ffprobe")

    def time_out(*args, **kwargs):
        raise subprocess.TimeoutExpired("ffprobe", 20)

    monkeypatch.setattr(media_module.subprocess, "run", time_out)

    with pytest.raises(MediaValidationError, match="metadata timed out"):
        probe_duration_ms(tmp_path / "clip.mp4")


def test_normalize_translates_timeout_and_removes_partial_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(media_module.shutil, "which", lambda _: "ffmpeg")
    destination = tmp_path / "normalized.mp4"
    destination.write_bytes(b"partial")

    def time_out(*args, **kwargs):
        raise subprocess.TimeoutExpired("ffmpeg", 90)

    monkeypatch.setattr(media_module.subprocess, "run", time_out)

    with pytest.raises(MediaValidationError, match="normalization timed out"):
        normalize_video(tmp_path / "source.mp4", destination)

    assert not destination.exists()


@pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="FFmpeg is not installed in this environment.",
)
def test_real_ffmpeg_probe_and_normalization(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    normalized = tmp_path / "normalized.mp4"

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=320x240:r=15",
            "-t",
            "5.2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(source),
        ],
        capture_output=True,
        check=True,
        timeout=30,
    )

    duration_ms = probe_duration_ms(source)
    normalize_video(source, normalized)

    assert 5_000 <= duration_ms <= 5_400
    assert normalized.exists()
    assert normalized.stat().st_size > 0
