import json
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


async def save_upload(
    upload: UploadFile,
    destination: Path,
    maximum_bytes: int,
) -> int:
    total_bytes = 0

    with destination.open("wb") as output:
        while chunk := await upload.read(1024 * 1024):
            total_bytes += len(chunk)

            if total_bytes > maximum_bytes:
                output.close()
                destination.unlink(missing_ok=True)

                raise MediaValidationError(
                    "The video is larger than the 30 MB limit.",
                )

            output.write(chunk)

    await upload.close()

    if total_bytes == 0:
        destination.unlink(missing_ok=True)
        raise MediaValidationError("The uploaded video is empty.")

    return total_bytes


def probe_duration_ms(video_path: Path) -> int:
    if shutil.which("ffprobe") is None:
        raise MediaValidationError(
            "FFprobe is unavailable on the backend.",
        )

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

    if result.returncode != 0:
        raise MediaValidationError(
            "The uploaded file is not a readable video.",
        )

    try:
        payload = json.loads(result.stdout)
        duration_seconds = float(payload["format"]["duration"])
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

    if result.returncode != 0 or not destination_path.exists():
        raise MediaValidationError(
            "The video could not be normalized.",
        )