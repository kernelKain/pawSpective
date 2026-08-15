import json
import math
import shutil
import subprocess
from pathlib import Path

from fastapi import UploadFile


ALLOWED_VIDEO_TYPES = {
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/quicktime": ".mov",
    "video/x-matroska": ".mkv",
}


class MediaValidationError(ValueError):
    pass


def format_megabytes(byte_count: int) -> str:
    megabytes = byte_count / (1024 * 1024)
    return f"{megabytes:g} MB"


async def save_upload(
    upload: UploadFile,
    destination: Path,
    maximum_bytes: int,
) -> int:
    total_bytes = 0

    try:
        with destination.open("wb") as output:
            while chunk := await upload.read(1024 * 1024):
                total_bytes += len(chunk)

                if total_bytes > maximum_bytes:
                    raise MediaValidationError(
                        "The video is larger than the "
                        f"{format_megabytes(maximum_bytes)} limit.",
                    )

                output.write(chunk)

        if total_bytes == 0:
            raise MediaValidationError("The uploaded video is empty.")

    except Exception:
        destination.unlink(missing_ok=True)
        raise

    finally:
        await upload.close()

    return total_bytes


def probe_duration_ms(video_path: Path) -> int:
    if shutil.which("ffprobe") is None:
        raise MediaValidationError(
            "FFprobe is unavailable on the backend.",
        )

    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                str(video_path),
            ],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise MediaValidationError(
            "Reading the video metadata timed out.",
        ) from error

    if result.returncode != 0:
        raise MediaValidationError(
            "The uploaded file is not a readable video.",
        )

    try:
        payload = json.loads(result.stdout)
        duration_seconds = float(payload["format"]["duration"])

        if not math.isfinite(duration_seconds) or duration_seconds <= 0:
            raise ValueError("duration must be finite and positive")
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise MediaValidationError(
            "The video duration could not be determined.",
        ) from error

    return round(duration_seconds * 1000)


def normalize_video(
    source_path: Path,
    destination_path: Path,
) -> None:
    if shutil.which("ffmpeg") is None:
        raise MediaValidationError(
            "FFmpeg is unavailable on the backend.",
        )

    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(source_path),
                "-an",
                "-vf",
                "scale=min(720\\,iw):-2,fps=15",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "23",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(destination_path),
            ],
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        destination_path.unlink(missing_ok=True)
        raise MediaValidationError(
            "Video normalization timed out.",
        ) from error

    if (
        result.returncode != 0
        or not destination_path.exists()
        or destination_path.stat().st_size == 0
    ):
        destination_path.unlink(missing_ok=True)
        raise MediaValidationError(
            "The video could not be normalized.",
        )
