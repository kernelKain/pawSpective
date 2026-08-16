import math
import shutil
import subprocess
from pathlib import Path

import cv2
import numpy as np

from backend.app.contracts import (
    SceneEvent,
    StoryReelRequest,
    StoryScriptResponse,
    VisibilityScore,
)
from backend.app.media import probe_duration_ms
from backend.app.visibility import canine_approximation


WIDTH = 720
HEIGHT = 1280
FPS = 15

FONT = cv2.FONT_HERSHEY_SIMPLEX

WHITE = (245, 245, 245)
CREAM = (232, 242, 246)
GREEN = (60, 86, 39)
LIME = (124, 235, 221)
YELLOW = (82, 200, 243)
BLUE = (201, 166, 118)
RED = (77, 101, 216)


class StoryRenderError(RuntimeError):
    pass


def wrap_text(text: str, maximum: int = 40) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current: list[str] = []

    for word in words:
        candidate = " ".join([*current, word])

        if current and len(candidate) > maximum:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)

    if current:
        lines.append(" ".join(current))

    return lines


def darken(frame: np.ndarray, amount: float) -> np.ndarray:
    overlay = np.zeros_like(frame)
    return cv2.addWeighted(
        frame,
        1.0 - amount,
        overlay,
        amount,
        0,
    )


def add_text(
    frame: np.ndarray,
    text: str,
    position: tuple[int, int],
    *,
    scale: float = 0.7,
    color: tuple[int, int, int] = WHITE,
    thickness: int = 2,
) -> None:
    cv2.putText(
        frame,
        text,
        position,
        FONT,
        scale,
        color,
        thickness,
        cv2.LINE_AA,
    )


def add_wrapped_text(
    frame: np.ndarray,
    text: str,
    x: int,
    y: int,
    *,
    maximum: int = 40,
    scale: float = 0.7,
    color: tuple[int, int, int] = WHITE,
    line_height: int = 38,
) -> None:
    for index, line in enumerate(
        wrap_text(text, maximum),
    ):
        add_text(
            frame,
            line,
            (x, y + index * line_height),
            scale=scale,
            color=color,
        )


def canine_frame(frame: np.ndarray) -> np.ndarray:
    rgb = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2RGB,
    ).astype(np.float32) / 255.0

    transformed = canine_approximation(
        rgb.reshape(-1, 3),
    ).reshape(rgb.shape)

    transformed_rgb = np.clip(
        transformed * 255.0,
        0,
        255,
    ).astype(np.uint8)

    return cv2.cvtColor(
        transformed_rgb,
        cv2.COLOR_RGB2BGR,
    )


def vertical_canvas(
    frame: np.ndarray,
) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    source_height, source_width = frame.shape[:2]

    cover_scale = max(
        WIDTH / source_width,
        HEIGHT / source_height,
    )
    cover_width = math.ceil(source_width * cover_scale)
    cover_height = math.ceil(source_height * cover_scale)

    blur_scale = 16
    blurred_width = max(
        1,
        math.ceil(cover_width / blur_scale),
    )
    blurred_height = max(
        1,
        math.ceil(cover_height / blur_scale),
    )

    background = cv2.resize(
        frame,
        (blurred_width, blurred_height),
        interpolation=cv2.INTER_AREA,
    )

    blurred_canvas_width = max(
        1,
        math.ceil(WIDTH / blur_scale),
    )
    blurred_canvas_height = max(
        1,
        math.ceil(HEIGHT / blur_scale),
    )
    crop_x = max(
        0,
        (blurred_width - blurred_canvas_width) // 2,
    )
    crop_y = max(
        0,
        (blurred_height - blurred_canvas_height) // 2,
    )

    background = background[
        crop_y : crop_y + blurred_canvas_height,
        crop_x : crop_x + blurred_canvas_width,
    ]
    background = cv2.GaussianBlur(
        background,
        (0, 0),
        sigmaX=2,
    )
    background = cv2.resize(
        background,
        (WIDTH, HEIGHT),
        interpolation=cv2.INTER_LINEAR,
    )
    background = darken(background, 0.35)

    contain_scale = min(
        (WIDTH - 48) / source_width,
        (HEIGHT - 180) / source_height,
    )
    content_width = max(
        1,
        round(source_width * contain_scale),
    )
    content_height = max(
        1,
        round(source_height * contain_scale),
    )

    content = cv2.resize(
        frame,
        (content_width, content_height),
        interpolation=cv2.INTER_AREA,
    )

    content_x = (WIDTH - content_width) // 2
    content_y = (HEIGHT - content_height) // 2

    background[
        content_y : content_y + content_height,
        content_x : content_x + content_width,
    ] = content

    return background, (
        content_x,
        content_y,
        content_width,
        content_height,
    )


def add_header(
    frame: np.ndarray,
    text: str,
    color: tuple[int, int, int],
) -> None:
    cv2.rectangle(
        frame,
        (24, 24),
        (WIDTH - 24, 88),
        (20, 30, 23),
        -1,
    )
    add_text(
        frame,
        text,
        (46, 68),
        scale=0.72,
        color=color,
    )


def add_subtitle(
    frame: np.ndarray,
    text: str,
) -> None:
    lines = wrap_text(text, 42)
    box_height = 44 + len(lines) * 38
    top = HEIGHT - box_height - 34

    overlay = frame.copy()
    cv2.rectangle(
        overlay,
        (30, top),
        (WIDTH - 30, HEIGHT - 30),
        (13, 22, 17),
        -1,
    )
    cv2.addWeighted(
        overlay,
        0.86,
        frame,
        0.14,
        0,
        frame,
    )

    for index, line in enumerate(lines):
        add_text(
            frame,
            line,
            (52, top + 48 + index * 38),
            scale=0.68,
        )


def add_event_overlays(
    frame: np.ndarray,
    rectangle: tuple[int, int, int, int],
    events: list[SceneEvent],
    scores: list[VisibilityScore],
    source_time_ms: int,
) -> None:
    left, top, width, height = rectangle
    scores_by_id = {
        score.event_id: score
        for score in scores
    }

    for event in events:
        if abs(event.timestamp_ms - source_time_ms) > 900:
            continue

        score = scores_by_id.get(event.event_id)

        if score is None:
            continue

        box = event.bounding_box

        x1 = left + round(box.x_min * width)
        y1 = top + round(box.y_min * height)
        x2 = left + round(box.x_max * width)
        y2 = top + round(box.y_max * height)

        color = (
            LIME
            if score.salience_level == "high"
            else YELLOW
            if score.salience_level == "medium"
            else BLUE
        )

        cv2.rectangle(
            frame,
            (x1, y1),
            (x2, y2),
            color,
            4,
        )

        label = (
            f"{event.object_label}  "
            f"{score.salience_score}/100"
        )
        label_width = min(
            WIDTH - x1 - 20,
            max(190, len(label) * 13),
        )

        cv2.rectangle(
            frame,
            (x1, max(0, y1 - 42)),
            (x1 + label_width, y1),
            (15, 24, 18),
            -1,
        )
        add_text(
            frame,
            label,
            (x1 + 10, y1 - 12),
            scale=0.5,
            color=color,
            thickness=1,
        )


def caption_for_time(
    story: StoryScriptResponse,
    current_seconds: float,
    total_seconds: int,
) -> str:
    start = 0.6
    end = max(start + 1, total_seconds - 3.2)

    if current_seconds < start or current_seconds >= end:
        return ""

    progress = (current_seconds - start) / (end - start)
    index = min(
        len(story.lines) - 1,
        int(progress * len(story.lines)),
    )

    return story.lines[index].text


def render_story_reel(
    video_path: Path,
    narration_path: Path,
    request: StoryReelRequest,
    story: StoryScriptResponse,
    destination: Path,
    duration_ms: int,
) -> None:
    if (
        shutil.which("ffmpeg") is None
        or shutil.which("ffprobe") is None
    ):
        raise StoryRenderError(
            "FFmpeg or FFprobe is unavailable on the backend.",
        )

    audio_duration_ms = probe_duration_ms(
        narration_path,
    )

    if audio_duration_ms > 23_000:
        raise StoryRenderError(
            "The narration is too long for a 25-second reel.",
        )

    reel_seconds = min(
        25,
        max(
            15,
            math.ceil(audio_duration_ms / 1000) + 2,
        ),
    )

    capture = cv2.VideoCapture(str(video_path))

    if not capture.isOpened():
        raise StoryRenderError(
            "The normalized video could not be opened.",
        )

    source_fps = capture.get(cv2.CAP_PROP_FPS) or FPS
    source_frame_count = max(
        1,
        round(capture.get(cv2.CAP_PROP_FRAME_COUNT)),
    )
    source_index = 0

    silent_path = destination.with_name(
        "story-silent.mp4",
    )

    writer = cv2.VideoWriter(
        str(silent_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        FPS,
        (WIDTH, HEIGHT),
    )

    if not writer.isOpened():
        capture.release()
        raise StoryRenderError(
            "The story video encoder could not be opened.",
        )

    scores_by_id = {
        score.event_id: score
        for score in request.scores
    }
    events_by_id = {
        event.event_id: event
        for event in request.events
    }

    featured_event = events_by_id[
        request.featured_event_id
    ]
    featured_score = scores_by_id[
        request.featured_event_id
    ]

    most_visible = max(
        request.scores,
        key=lambda score: score.dog_contrast_score,
    )
    biggest_movement = max(
        request.scores,
        key=lambda score: score.motion_score,
    )

    most_visible_event = events_by_id[
        most_visible.event_id
    ]
    biggest_movement_event = events_by_id[
        biggest_movement.event_id
    ]

    total_frames = reel_seconds * FPS
    intro_end = 2.0
    human_end = 5.0
    dog_end = 9.0
    outro_start = reel_seconds - 4.0

    try:
        for frame_number in range(total_frames):
            if source_index >= source_frame_count:
                capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                source_index = 0

            ok, source = capture.read()

            if not ok:
                capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                source_index = 0
                ok, source = capture.read()

            if not ok:
                raise StoryRenderError(
                    "A source video frame could not be read.",
                )

            source_time_ms = round(
                source_index / source_fps * 1000,
            )
            source_time_ms = min(
                source_time_ms,
                max(0, duration_ms - 1),
            )
            source_index += 1

            current_seconds = frame_number / FPS

            human, _ = vertical_canvas(source)
            dog = human
            dog_rect = (0, 0, WIDTH, HEIGHT)

            if current_seconds >= human_end:
                dog_source = canine_frame(source)
                dog, dog_rect = vertical_canvas(dog_source)

            if current_seconds < intro_end:
                frame = darken(human, 0.7)

                add_text(
                    frame,
                    "PAWSPECTIVE PRESENTS",
                    (60, 170),
                    scale=0.65,
                    color=LIME,
                )
                add_wrapped_text(
                    frame,
                    story.title.upper(),
                    60,
                    280,
                    maximum=22,
                    scale=1.15,
                    line_height=66,
                )
                add_text(
                    frame,
                    (
                        f"{request.profile.age} "
                        f"{request.profile.dog_name}"
                    ),
                    (60, 480),
                    scale=0.75,
                    color=CREAM,
                )
                add_text(
                    frame,
                    "JUST FOR FUN - FICTIONAL DOG VOICE",
                    (60, 560),
                    scale=0.5,
                    color=YELLOW,
                    thickness=1,
                )

            elif current_seconds < human_end:
                frame = human
                add_header(
                    frame,
                    "ORIGINAL HUMAN VIEW",
                    WHITE,
                )

            elif current_seconds < dog_end:
                transition = min(
                    1.0,
                    max(
                        0.0,
                        current_seconds - human_end,
                    ),
                )
                split = round(WIDTH * transition)

                frame = human.copy()
                frame[:, :split] = dog[:, :split]

                cv2.line(
                    frame,
                    (split, 100),
                    (split, HEIGHT - 100),
                    WHITE,
                    4,
                )
                add_header(
                    frame,
                    "CANINE-VISION APPROXIMATION",
                    LIME,
                )

            elif current_seconds < outro_start:
                frame = dog
                add_header(
                    frame,
                    "POSSIBLE ATTENTION CUES",
                    YELLOW,
                )
                add_event_overlays(
                    frame,
                    dog_rect,
                    request.events,
                    request.scores,
                    source_time_ms,
                )

            else:
                frame = darken(dog, 0.78)

                add_text(
                    frame,
                    f"{request.profile.dog_name.upper()}'S WORLD",
                    (54, 170),
                    scale=1.0,
                    color=LIME,
                )

                add_wrapped_text(
                    frame,
                    (
                        "Most visible object: "
                        f"{most_visible_event.object_label}"
                    ),
                    54,
                    300,
                    maximum=34,
                    scale=0.72,
                )
                add_wrapped_text(
                    frame,
                    (
                        "Biggest movement: "
                        f"{biggest_movement_event.object_label}"
                    ),
                    54,
                    420,
                    maximum=34,
                    scale=0.72,
                )
                add_wrapped_text(
                    frame,
                    (
                        f"Featured: {featured_event.object_label} - "
                        f"{featured_score.dog_contrast_score}/100 "
                        "dog-visible contrast"
                    ),
                    54,
                    540,
                    maximum=34,
                    scale=0.72,
                )

                add_text(
                    frame,
                    "Created with PawSpective",
                    (54, 720),
                    scale=0.62,
                    color=YELLOW,
                )
                add_wrapped_text(
                    frame,
                    (
                        "Canine-vision approximation. Fictional "
                        "narration. No gaze or thought detection."
                    ),
                    54,
                    800,
                    maximum=42,
                    scale=0.52,
                    color=CREAM,
                    line_height=32,
                )

            subtitle = caption_for_time(
                story,
                current_seconds,
                reel_seconds,
            )

            if subtitle and current_seconds < outro_start:
                add_subtitle(frame, subtitle)

            writer.write(frame)

    finally:
        capture.release()
        writer.release()

    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(silent_path),
            "-i",
            str(narration_path),
            "-filter_complex",
            "[1:a]apad=pad_dur=2[audio]",
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
        ],
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )

    silent_path.unlink(missing_ok=True)

    if result.returncode != 0 or not destination.exists():
        raise StoryRenderError(
            "FFmpeg could not finish the Story Reel.",
        )
