import math
import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from backend.app.contracts import StoryReelRequest, StoryScriptResponse
from backend.app.media import probe_duration_ms
from backend.app.visibility import canine_approximation


WIDTH = 720
HEIGHT = 1280
FPS = 24
NARRATION_TARGET_LUFS = -16
MUSIC_TARGET_LUFS = -30
MUSIC_TRACKS = (
    ("sunny-paws", (261.63, 329.63, 392.00)),
    ("curious-steps", (293.66, 369.99, 440.00)),
    ("cozy-walk", (220.00, 277.18, 329.63)),
)


class StoryRenderError(RuntimeError):
    pass


def music_track_id(animation_seed: int) -> str:
    return MUSIC_TRACKS[animation_seed % len(MUSIC_TRACKS)][0]


def ping_pong_frame_index(
    output_frame: int,
    output_fps: float,
    source_fps: float,
    source_frame_count: int,
) -> int:
    """Map reel time onto adjacent source frames without freezing at the end."""
    if source_frame_count <= 1:
        return 0

    chronological_index = round(output_frame / output_fps * source_fps)
    period = 2 * (source_frame_count - 1)
    phase = chronological_index % period
    return phase if phase < source_frame_count else period - phase


def canine_frame(frame: np.ndarray) -> np.ndarray:
    """Apply the same dichromatic approximation used elsewhere in the app."""
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    transformed = canine_approximation(rgb.reshape(-1, 3)).reshape(rgb.shape)
    transformed_rgb = np.clip(transformed * 255.0, 0, 255).astype(np.uint8)
    return cv2.cvtColor(transformed_rgb, cv2.COLOR_RGB2BGR)


def sketch_frame(frame: np.ndarray, seed: int, frame_number: int) -> np.ndarray:
    """Create a warm, text-free hand-drawn treatment with seeded variation."""
    canine = canine_frame(frame)
    treatment = seed % 3
    smoothed = cv2.bilateralFilter(
        canine,
        d=7 + treatment * 2,
        sigmaColor=45 + treatment * 12,
        sigmaSpace=45 + treatment * 10,
    )
    levels = (32, 40, 48)[treatment]
    painted = np.clip((smoothed // levels) * levels + levels // 2, 0, 255).astype(
        np.uint8
    )

    gray = cv2.cvtColor(canine, cv2.COLOR_BGR2GRAY)
    gray = cv2.medianBlur(gray, 5)
    edges = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        9 + treatment * 2,
        5,
    )
    edges = cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)
    sketch = cv2.bitwise_and(painted, edges)

    paper = np.full_like(sketch, (214 + treatment * 4, 230, 238))
    sketch = cv2.addWeighted(sketch, 0.88, paper, 0.12, 0)

    # A tiny seeded line wobble provides real visual variation without changing
    # source timing, event geometry, or the action represented by each frame.
    phase = (frame_number // 3 + seed) % 7
    dx = (-2, 1, 0, 2, -1, 1, 0)[phase]
    dy = (0, -1, 1, 0, 2, -2, 1)[phase]
    transform = np.float32([[1, 0, dx], [0, 1, dy]])
    return cv2.warpAffine(
        sketch,
        transform,
        (sketch.shape[1], sketch.shape[0]),
        borderMode=cv2.BORDER_REFLECT,
    )


def vertical_canvas(frame: np.ndarray) -> np.ndarray:
    source_height, source_width = frame.shape[:2]
    cover_scale = max(WIDTH / source_width, HEIGHT / source_height)
    cover_size = (
        max(1, math.ceil(source_width * cover_scale)),
        max(1, math.ceil(source_height * cover_scale)),
    )
    background = cv2.resize(frame, cover_size, interpolation=cv2.INTER_AREA)
    x = max(0, (background.shape[1] - WIDTH) // 2)
    y = max(0, (background.shape[0] - HEIGHT) // 2)
    background = background[y : y + HEIGHT, x : x + WIDTH]
    background = cv2.GaussianBlur(background, (0, 0), sigmaX=18)
    background = cv2.addWeighted(background, 0.62, np.zeros_like(background), 0.38, 0)

    contain_scale = min((WIDTH - 40) / source_width, (HEIGHT - 80) / source_height)
    content_width = max(1, round(source_width * contain_scale))
    content_height = max(1, round(source_height * contain_scale))
    content = cv2.resize(
        frame, (content_width, content_height), interpolation=cv2.INTER_AREA
    )
    content_x = (WIDTH - content_width) // 2
    content_y = (HEIGHT - content_height) // 2
    background[
        content_y : content_y + content_height,
        content_x : content_x + content_width,
    ] = content
    return background


def _music_source(seed: int, duration: int) -> str:
    _, frequencies = MUSIC_TRACKS[seed % len(MUSIC_TRACKS)]
    pace = (1.8, 2.15, 1.55)[seed % 3]
    tones = "+".join(
        f"0.055*sin(2*PI*{frequency}*t)*(0.72+0.28*sin(2*PI*{pace}*t))"
        for frequency in frequencies
    )
    return f"aevalsrc={tones}:s=44100:d={duration}"


def _wrapped_caption(text: str, maximum: int = 34) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > maximum:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines[:2]


def _draw_monologue_overlay(
    frame: np.ndarray,
    caption: str,
) -> np.ndarray:
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, HEIGHT - 250), (WIDTH, HEIGHT), (18, 24, 29), -1)
    frame = cv2.addWeighted(overlay, 0.68, frame, 0.32, 0)
    lines = _wrapped_caption(caption)
    first_y = HEIGHT - 170 - max(0, len(lines) - 1) * 28
    for offset, line in enumerate(lines):
        size = cv2.getTextSize(line, cv2.FONT_HERSHEY_DUPLEX, 0.82, 2)[0]
        x = max(28, (WIDTH - size[0]) // 2)
        y = first_y + offset * 58
        cv2.putText(
            frame,
            line,
            (x, y),
            cv2.FONT_HERSHEY_DUPLEX,
            0.82,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
    footer = "Fictional AI dog monologue"
    size = cv2.getTextSize(footer, cv2.FONT_HERSHEY_SIMPLEX, 0.43, 1)[0]
    cv2.putText(
        frame,
        footer,
        ((WIDTH - size[0]) // 2, HEIGHT - 28),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.43,
        (210, 220, 225),
        1,
        cv2.LINE_AA,
    )
    return frame


def render_animated_story_reel(
    animation_path: Path,
    narration_path: Path,
    request: StoryReelRequest,
    story: StoryScriptResponse,
    destination: Path,
    check_cancelled: Callable[[], None] = lambda: None,
) -> None:
    """Compose one generated animation with the complete fictional monologue."""
    check_cancelled()
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise StoryRenderError("FFmpeg or FFprobe is unavailable on the backend.")

    animation_duration_ms = probe_duration_ms(animation_path)
    audio_duration_ms = probe_duration_ms(narration_path)
    if not 5_000 <= animation_duration_ms <= 11_000:
        raise StoryRenderError("The generated animation has an invalid duration.")
    if audio_duration_ms > animation_duration_ms + 250:
        raise StoryRenderError("The monologue is too long for the generated animation.")

    capture = cv2.VideoCapture(str(animation_path))
    if not capture.isOpened():
        raise StoryRenderError("The generated animation could not be opened.")
    source_fps = capture.get(cv2.CAP_PROP_FPS) or FPS
    source_frames = max(1, round(capture.get(cv2.CAP_PROP_FRAME_COUNT)))
    silent_path = destination.with_name("animated-captioned.mp4")
    writer = cv2.VideoWriter(
        str(silent_path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (WIDTH, HEIGHT)
    )
    if not writer.isOpened():
        capture.release()
        raise StoryRenderError("The animated reel could not be created.")

    output_frames = max(1, round(animation_duration_ms / 1000 * FPS))
    try:
        for frame_number in range(output_frames):
            check_cancelled()
            source_index = min(
                source_frames - 1,
                round(frame_number / FPS * source_fps),
            )
            capture.set(cv2.CAP_PROP_POS_FRAMES, source_index)
            ok, frame = capture.read()
            if not ok or frame is None:
                raise StoryRenderError("A generated animation frame could not be read.")
            line_index = min(
                len(story.lines) - 1,
                frame_number * len(story.lines) // output_frames,
            )
            writer.write(
                _draw_monologue_overlay(
                    vertical_canvas(frame),
                    story.lines[line_index].text,
                )
            )
    finally:
        capture.release()
        writer.release()

    reel_seconds = animation_duration_ms / 1000
    fade_out_start = max(0.0, reel_seconds - 1.0)
    filter_graph = (
        f"[1:a]loudnorm=I={NARRATION_TARGET_LUFS}:LRA=9:TP=-1.5,"
        f"apad=whole_dur={reel_seconds:.3f}[voice];"
        f"[2:a]loudnorm=I={MUSIC_TARGET_LUFS}:LRA=7:TP=-3,volume=0.16,"
        f"afade=t=in:st=0:d=0.6,afade=t=out:st={fade_out_start:.3f}:d=1[music];"
        "[voice][music]amix=inputs=2:duration=first:dropout_transition=1:normalize=0,"
        "alimiter=limit=0.95[audio]"
    )
    command = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(silent_path),
        "-i", str(narration_path),
        "-f", "lavfi", "-i", _music_source(request.animation_seed, math.ceil(reel_seconds)),
        "-filter_complex", filter_graph,
        "-map", "0:v:0", "-map", "[audio]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-pix_fmt", "yuv420p", "-r", str(FPS),
        "-c:a", "aac", "-b:a", "160k",
        "-t", f"{reel_seconds:.3f}", "-movflags", "+faststart",
        str(destination),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, timeout=120)
        check_cancelled()
    except Exception as error:
        destination.unlink(missing_ok=True)
        raise StoryRenderError("The animated Story Reel could not be completed.") from error
    finally:
        silent_path.unlink(missing_ok=True)
    if not destination.is_file() or destination.stat().st_size == 0:
        raise StoryRenderError("The animated Story Reel output was not created.")


def render_story_reel(
    video_path: Path,
    narration_path: Path,
    request: StoryReelRequest,
    story: StoryScriptResponse,
    destination: Path,
    duration_ms: int,
    check_cancelled: Callable[[], None] = lambda: None,
) -> None:
    """Render a text-free sketch reel and safely mix narration with music."""
    del story  # Narration is audio-only; no generated text is drawn into video.
    check_cancelled()

    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise StoryRenderError("FFmpeg or FFprobe is unavailable on the backend.")

    audio_duration_ms = probe_duration_ms(narration_path)
    if audio_duration_ms > 18_000:
        raise StoryRenderError("The narration is too long for this reel.")

    voice_speed = max(1.0, audio_duration_ms / 9_000)
    fitted_audio_ms = audio_duration_ms / voice_speed
    reel_seconds = min(10, max(8, math.ceil(fitted_audio_ms / 1000) + 1))
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise StoryRenderError("The prepared video could not be opened.")

    source_fps = capture.get(cv2.CAP_PROP_FPS) or FPS
    source_frame_count = max(1, round(capture.get(cv2.CAP_PROP_FRAME_COUNT)))
    duration_frame_count = max(1, round(duration_ms / 1000 * source_fps))
    usable_source_frames = min(source_frame_count, duration_frame_count)
    silent_path = destination.with_name("story-silent.mp4")
    writer = cv2.VideoWriter(
        str(silent_path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (WIDTH, HEIGHT)
    )
    if not writer.isOpened():
        capture.release()
        raise StoryRenderError("The sketch video could not be created.")

    source_index = 0
    last_source: np.ndarray | None = None

    try:
        for frame_number in range(reel_seconds * FPS):
            check_cancelled()
            target_source_index = ping_pong_frame_index(
                frame_number,
                FPS,
                source_fps,
                usable_source_frames,
            )
            if target_source_index != source_index or last_source is None:
                capture.set(cv2.CAP_PROP_POS_FRAMES, target_source_index)
                ok, candidate = capture.read()
                if ok and candidate is not None:
                    last_source = candidate
                    source_index = target_source_index
            if last_source is None:
                raise StoryRenderError("A source video frame could not be read.")

            animated = sketch_frame(last_source, request.animation_seed, frame_number)
            writer.write(vertical_canvas(animated))
    finally:
        capture.release()
        writer.release()

    fade_out_start = max(0.0, reel_seconds - 1.5)
    filter_graph = (
        f"[1:a]atempo={voice_speed:.4f},"
        f"loudnorm=I={NARRATION_TARGET_LUFS}:LRA=9:TP=-1.5,"
        f"apad=whole_dur={reel_seconds}[voice];"
        f"[2:a]loudnorm=I={MUSIC_TARGET_LUFS}:LRA=7:TP=-3,volume=0.18,"
        f"afade=t=in:st=0:d=1.2,afade=t=out:st={fade_out_start}:d=1.5[music];"
        "[voice][music]amix=inputs=2:duration=first:dropout_transition=1:normalize=0,"
        "alimiter=limit=0.95[audio]"
    )

    command = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(silent_path),
        "-i",
        str(narration_path),
        "-f",
        "lavfi",
        "-i",
        _music_source(request.animation_seed, reel_seconds),
        "-filter_complex",
        filter_graph,
        "-map",
        "0:v:0",
        "-map",
        "[audio]",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "22",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-t",
        str(reel_seconds),
        "-movflags",
        "+faststart",
        str(destination),
    ]
    process: subprocess.Popen[bytes] | None = None

    try:
        check_cancelled()
        process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + 120
        while process.poll() is None:
            check_cancelled()
            if time.monotonic() >= deadline:
                raise StoryRenderError("The Story Reel took too long to finish.")
            time.sleep(0.1)
        return_code = process.returncode
        check_cancelled()
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        silent_path.unlink(missing_ok=True)

    if (
        return_code != 0
        or not destination.exists()
        or destination.stat().st_size == 0
    ):
        destination.unlink(missing_ok=True)
        raise StoryRenderError("The Story Reel could not be completed.")
