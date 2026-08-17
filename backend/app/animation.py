import base64
import logging
import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable, Literal

import cv2
import httpx
from google import genai
from google.genai import types

from backend.app.cancellable import run_cancellable_process
from backend.app.contracts import StoryReelRequest, StoryScriptResponse
from backend.app.settings import settings


VisualSource = Literal[
    "gemini_omni",
    "veo_3_1",
    "local_animation_fallback",
    "controlled_demo_cache",
]

logger = logging.getLogger(__name__)

DEFAULT_CREATIVE_DIRECTION = (
    "Cinematic hand-painted 2.5D animation with softly textured surfaces, "
    "fluid natural motion, polished lighting, stable geometry, and a warm "
    "feel-good finish."
)

UNSAFE_CREATIVE_DIRECTION_PHRASES = (
    "exactly what a dog sees",
    "dog's thoughts",
    "dogs thoughts",
    "dog thinks",
    "dog feels",
    "dog wants",
    "dog knows",
    "dog smells",
    "dog's gaze",
    "dogs gaze",
    "third-person",
    "external view",
    "show the dog",
    "add a",
    "add an",
    "remove the",
    "replace the",
    "duplicate the",
    "ignore the",
    "omit the",
)


class AnimationGenerationError(RuntimeError):
    pass


def safe_creative_direction(value: str | None) -> str:
    """Accept style guidance only when it cannot override grounded scene rules."""
    if not value:
        return DEFAULT_CREATIVE_DIRECTION
    normalized = " ".join(value.split())
    lowered = normalized.casefold()
    if any(phrase in lowered for phrase in UNSAFE_CREATIVE_DIRECTION_PHRASES):
        return DEFAULT_CREATIVE_DIRECTION
    return normalized


def prepare_animation_source(
    source_path: Path,
    destination: Path,
    request: StoryReelRequest,
    duration_ms: int,
) -> int:
    """Create the provider input, capped at ten seconds around the feature."""
    if shutil.which("ffmpeg") is None:
        raise AnimationGenerationError("FFmpeg is unavailable for animation preparation.")
    target_ms = min(10_000, duration_ms)
    featured = next(
        event for event in request.events if event.event_id == request.featured_event_id
    )
    start_ms = max(0, min(duration_ms - target_ms, featured.timestamp_ms - target_ms // 2))
    command = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-ss",
        f"{start_ms / 1000:.3f}",
        "-i",
        str(source_path),
        "-t",
        f"{target_ms / 1000:.3f}",
        "-vf",
        "scale='min(1280,iw)':-2:flags=lanczos",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(destination),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as error:
        destination.unlink(missing_ok=True)
        raise AnimationGenerationError("The animation source could not be prepared.") from error
    if not destination.is_file() or destination.stat().st_size == 0:
        raise AnimationGenerationError("The animation source was not created.")
    return target_ms


def build_animation_prompt(
    request: StoryReelRequest,
    story: StoryScriptResponse,
) -> str:
    events = "\n".join(
        f"- {event.object_label}: {event.visible_evidence}; "
        f"motion={event.motion_level.value}"
        for event in request.events
    )
    beats = "\n".join(
        f"- {line.text}"
        for line in story.lines
    )
    creative_direction = safe_creative_direction(story.animation_prompt)
    camera_height = {
        "Small": "30 centimetres",
        "Medium": "45 centimetres",
        "Large": "60 centimetres",
    }[request.profile.size]

    return f"""Transform the supplied scene into a polished animated film clip.

CREATIVE DIRECTION:
{creative_direction}

VIEWPOINT:
Use one continuous first-person viewpoint at approximately {camera_height}
above the ground. The camera represents an artistic dog-height point of view.
Use smooth, subtle head movement. Never show the dog from an external angle.

VISIBLE SCENE FACTS TO PRESERVE:
{events}

MONOLOGUE PACING TO SUPPORT VISUALLY:
{beats}

VISUAL STYLE:
Cinematic hand-painted 2.5D animation, cohesive art direction, softly textured
surfaces, elegant depth, expressive environmental movement, fluid natural
animation, stable subject identity, and aesthetically composed lighting.

CANINE-VISION-INSPIRED COLOR:
Use a restrained blue-yellow dominant palette. Reduce red-green separation
while preserving brightness, readable silhouettes, and object boundaries.
This is an artistic approximation, not an exact biological simulation.

PRESERVATION RULES:
Preserve every visible person, animal, toy, object, identity, object count,
background relationship, movement direction, and chronological action. Do not
add, remove, replace, duplicate, or merge subjects. Do not invent an outcome.

OUTPUT RULES:
Create a single continuous 9:16 portrait shot, 8 to 10 seconds, with no cuts.
No text, subtitles, title cards, logos, dialogue, narration, barking, music, or
new sound effects. No excessive camera shake, malformed anatomy, duplicated
objects, or abrupt style changes. Keep the scene upbeat, charming, and warm.
""".strip()


def _wait_for_uploaded_file(client: genai.Client, uploaded: types.File) -> types.File:
    deadline = time.monotonic() + 120
    current = uploaded
    while str(current.state).upper().endswith("PROCESSING"):
        if time.monotonic() >= deadline:
            raise RuntimeError("Gemini did not finish processing the source video.")
        time.sleep(2)
        if not current.name:
            raise RuntimeError("Gemini returned an unnamed source file.")
        current = client.files.get(name=current.name)
    if str(current.state).upper().endswith("FAILED") or not current.uri:
        raise RuntimeError("Gemini could not process the source video.")
    return current


def _download_uri(uri: str, api_key: str) -> bytes:
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        response = client.get(uri, headers={"x-goog-api-key": api_key})
        response.raise_for_status()
        return response.content


def _wait_for_output_uri(client: genai.Client, uri: str) -> bytes:
    file_id = uri.rstrip("/").rsplit("/", 1)[-1]
    if not file_id:
        raise RuntimeError("Gemini Omni returned an invalid video URI.")
    deadline = time.monotonic() + 180
    while True:
        file_info = client.files.get(name=f"files/{file_id}")
        state = str(file_info.state).upper()
        if state.endswith("ACTIVE"):
            return client.files.download(file=uri)
        if state.endswith("FAILED"):
            raise RuntimeError("Gemini Omni could not prepare the generated video.")
        if time.monotonic() >= deadline:
            raise RuntimeError("Gemini Omni video download timed out.")
        time.sleep(5)


def _omni_output_bytes(
    interaction: object,
    client: genai.Client,
    api_key: str,
) -> bytes:
    output_video = getattr(interaction, "output_video", None)
    if output_video is not None:
        data = getattr(output_video, "data", None)
        if data:
            return base64.b64decode(data)
        uri = getattr(output_video, "uri", None)
        if uri:
            return _wait_for_output_uri(client, uri)

    if hasattr(interaction, "model_dump"):
        payload = interaction.model_dump(mode="python")
        stack: list[object] = [payload]
        while stack:
            value = stack.pop()
            if isinstance(value, dict):
                mime_type = value.get("mime_type") or value.get("mimeType")
                if mime_type == "video/mp4":
                    data = value.get("data")
                    if isinstance(data, str) and data:
                        return base64.b64decode(data)
                    uri = value.get("uri")
                    if isinstance(uri, str) and uri:
                        return _download_uri(uri, api_key)
                stack.extend(value.values())
            elif isinstance(value, list):
                stack.extend(value)
    raise RuntimeError("Gemini Omni returned no downloadable video.")


def _request_omni_animation(
    api_key: str,
    model: str,
    source_path: str,
    prompt: str,
    destination: str,
) -> str:
    client = genai.Client(api_key=api_key)
    try:
        uploaded = _wait_for_uploaded_file(
            client,
            client.files.upload(file=source_path),
        )
        interaction = client.interactions.create(
            model=model,
            store=False,
            input=[
                {"type": "document", "uri": uploaded.uri},
                {"type": "text", "text": prompt},
            ],
            response_format={
                "type": "video",
                "aspect_ratio": "9:16",
                "delivery": "uri",
            },
            generation_config={
                "video_config": {"task": "edit"},
            },
        )
        output = _omni_output_bytes(interaction, client, api_key)
        if len(output) < 10_000:
            raise RuntimeError("Gemini Omni returned an incomplete video.")
        Path(destination).write_bytes(output)
        return model
    finally:
        client.close()


def extract_reference_frames(source_path: Path, directory: Path) -> list[Path]:
    capture = cv2.VideoCapture(str(source_path))
    if not capture.isOpened():
        raise AnimationGenerationError("Reference frames could not be extracted.")
    frame_count = max(1, round(capture.get(cv2.CAP_PROP_FRAME_COUNT)))
    indices = sorted({0, frame_count // 2, frame_count - 1})
    paths: list[Path] = []
    try:
        for order, index in enumerate(indices):
            capture.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, frame = capture.read()
            if not ok or frame is None:
                continue
            path = directory / f"reference-{order}.jpg"
            if not cv2.imwrite(str(path), frame, [cv2.IMWRITE_JPEG_QUALITY, 92]):
                continue
            paths.append(path)
    finally:
        capture.release()
    if not paths:
        raise AnimationGenerationError("No usable animation reference frame was found.")
    return paths


def _request_veo_animation(
    api_key: str,
    model: str,
    reference_paths: tuple[str, ...],
    prompt: str,
    seed: int,
    destination: str,
) -> str:
    client = genai.Client(api_key=api_key)
    try:
        references = [
            types.VideoGenerationReferenceImage(
                image=types.Image(
                    image_bytes=Path(path).read_bytes(),
                    mime_type="image/jpeg",
                ),
                reference_type="asset",
            )
            for path in reference_paths[:3]
        ]
        operation = client.models.generate_videos(
            model=model,
            prompt=prompt,
            config=types.GenerateVideosConfig(
                number_of_videos=1,
                duration_seconds=8,
                seed=seed,
                aspect_ratio="9:16",
                resolution="720p",
                reference_images=references,
                generate_audio=False,
                person_generation="allow_adult",
            ),
        )
        deadline = time.monotonic() + 360
        while not operation.done:
            if time.monotonic() >= deadline:
                raise RuntimeError("Veo generation timed out.")
            time.sleep(5)
            operation = client.operations.get(operation)
        response = operation.response or operation.result
        generated = response.generated_videos if response else None
        if not generated or not generated[0].video:
            raise RuntimeError("Veo returned no generated video.")
        output = client.files.download(file=generated[0].video)
        if len(output) < 10_000:
            raise RuntimeError("Veo returned an incomplete video.")
        Path(destination).write_bytes(output)
        return model
    finally:
        client.close()


def generate_animated_video(
    source_path: Path,
    destination: Path,
    prompt: str,
    request: StoryReelRequest,
    work_directory: Path,
    check_cancelled: Callable[[], None],
) -> tuple[VisualSource, str]:
    if settings.demo_mode or not settings.animation_enabled:
        raise AnimationGenerationError("Live animation generation is disabled.")
    if not settings.gemini_api_key:
        raise AnimationGenerationError("Gemini animation is not configured.")

    try:
        if request.animation_provider == "gemini_omni":
            arguments = (
                settings.gemini_api_key,
                settings.omni_video_model,
                str(source_path),
                prompt,
                str(destination),
            )
            model = run_cancellable_process(
                _request_omni_animation,
                arguments,
                check_cancelled,
                timeout_seconds=settings.animation_timeout_seconds,
            )
            source: VisualSource = "gemini_omni"
        else:
            references = extract_reference_frames(source_path, work_directory)
            arguments = (
                settings.gemini_api_key,
                settings.veo_video_model,
                tuple(str(path) for path in references),
                prompt,
                request.animation_seed,
                str(destination),
            )
            model = run_cancellable_process(
                _request_veo_animation,
                arguments,
                check_cancelled,
                timeout_seconds=settings.animation_timeout_seconds,
            )
            source = "veo_3_1"
        check_cancelled()
        if not destination.is_file() or destination.stat().st_size == 0:
            raise AnimationGenerationError("The animated video was not created.")
        return source, str(model)
    except Exception as error:
        destination.unlink(missing_ok=True)
        check_cancelled()
        logger.exception("Animated video generation failed")
        if isinstance(error, AnimationGenerationError):
            raise
        raise AnimationGenerationError("Animated video generation failed.") from error
