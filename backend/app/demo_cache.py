import hashlib
import json
import shutil
from pathlib import Path

from backend.app.contracts import (
    SceneAnalysisResponse,
    SceneEvent,
    StoryReelRequest,
    StoryScriptResponse,
)
from backend.app.media import probe_duration_ms
from backend.app.settings import settings


CLIP_FILENAME = "controlled-demo.mp4"
ANALYSIS_FILENAME = "analysis.json"
STORY_REQUEST_FILENAME = "story-request.json"
NARRATION_FILENAME = "narration.mp3"
REEL_FILENAME = "completed-reel.mp4"
STORY_FILENAME = "story.json"
MANIFEST_FILENAME = "manifest.json"

REQUIRED_FILES = (
    CLIP_FILENAME,
    ANALYSIS_FILENAME,
    STORY_REQUEST_FILENAME,
    NARRATION_FILENAME,
    REEL_FILENAME,
    STORY_FILENAME,
    MANIFEST_FILENAME,
)
HASH_FIELDS = {
    CLIP_FILENAME: "clip_sha256",
    ANALYSIS_FILENAME: "analysis_sha256",
    STORY_REQUEST_FILENAME: "story_request_sha256",
    NARRATION_FILENAME: "narration_sha256",
    REEL_FILENAME: "reel_sha256",
    STORY_FILENAME: "story_sha256",
}
MUSIC_TRACK_IDS = ("sunny-paws", "curious-steps", "cozy-walk")


class DemoCacheError(RuntimeError):
    pass


def cache_path(filename: str) -> Path:
    return settings.demo_cache_directory / filename


def fingerprint(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def available() -> bool:
    if not settings.controlled_demo_enabled or not all(
        cache_path(filename).is_file()
        for filename in REQUIRED_FILES
    ):
        return False

    try:
        payload = manifest()
        if payload.get("cache_version") != "2.0":
            return False
        if payload.get("provenance") != "pawspective-controlled-demo-v2":
            return False
        if any(
            payload.get(field) != fingerprint(cache_path(filename))
            for filename, field in HASH_FIELDS.items()
        ):
            return False

        request = cached_story_request()
        cached_analysis = analysis()
        story = cached_story()
        relationships_match = (
            request.analysis_source == "controlled_demo"
            and request.events == cached_analysis.events
            and payload.get("duration_ms") == cached_analysis.duration_ms
            and payload.get("variation_id") == request.variation_id
            and payload.get("animation_seed") == request.animation_seed
            and payload.get("music_track_id")
            == MUSIC_TRACK_IDS[request.animation_seed % len(MUSIC_TRACK_IDS)]
            and payload.get("voice_source") == "controlled_demo_cache"
            and payload.get("analysis_source") == "gemini"
            and payload.get("story_source") == "gemini"
            and payload.get("profile") == request.profile.model_dump(mode="json")
        )
        if not relationships_match:
            return False

        clip_duration_ms = probe_duration_ms(cache_path(CLIP_FILENAME))
        narration_duration_ms = probe_duration_ms(cache_path(NARRATION_FILENAME))
        reel_duration_ms = probe_duration_ms(cache_path(REEL_FILENAME))
        if (
            clip_duration_ms != cached_analysis.duration_ms
            or narration_duration_ms > 23_000
            or not 15_000 <= reel_duration_ms <= 25_000
        ):
            return False

        # Import locally so lightweight cache metadata consumers do not load the
        # provider SDK unless all cheaper cache checks have already succeeded.
        from backend.app.story import (
            StoryGenerationError,
            validate_story_grounding,
        )

        try:
            validate_story_grounding(story, request)
        except StoryGenerationError as error:
            raise DemoCacheError(
                "The controlled demo story no longer matches its request."
            ) from error
        return True
    except (DemoCacheError, OSError, ValueError):
        return False


def _read_json(filename: str) -> object:
    try:
        return json.loads(cache_path(filename).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DemoCacheError(
            f"The controlled demo cache file {filename} is invalid."
        ) from error


def manifest() -> dict[str, object]:
    payload = _read_json(MANIFEST_FILENAME)

    if not isinstance(payload, dict):
        raise DemoCacheError("The controlled demo manifest is invalid.")

    return payload


def matches_clip(path: Path) -> bool:
    if not available():
        return False

    try:
        expected = manifest().get("clip_sha256")
        return isinstance(expected, str) and fingerprint(path) == expected
    except (DemoCacheError, OSError):
        return False


def require_matching_clip(path: Path) -> None:
    if not available():
        raise DemoCacheError("The controlled demo cache is incomplete.")

    if not matches_clip(path):
        raise DemoCacheError(
            "The uploaded clip does not match the controlled demo asset."
        )


def analysis() -> SceneAnalysisResponse:
    payload = _read_json(ANALYSIS_FILENAME)

    try:
        return SceneAnalysisResponse.model_validate(payload)
    except ValueError as error:
        raise DemoCacheError(
            "The controlled demo analysis is invalid."
        ) from error


def cached_story_request() -> StoryReelRequest:
    payload = _read_json(STORY_REQUEST_FILENAME)

    try:
        return StoryReelRequest.model_validate(payload)
    except ValueError as error:
        raise DemoCacheError(
            "The controlled demo story request is invalid."
        ) from error


def cached_story() -> StoryScriptResponse:
    payload = _read_json(STORY_FILENAME)

    try:
        return StoryScriptResponse.model_validate(payload)
    except ValueError as error:
        raise DemoCacheError(
            "The controlled demo story is invalid."
        ) from error


def _event_provenance(event: SceneEvent) -> dict[str, object]:
    return event.model_dump(
        mode="json",
        exclude={"object_label"},
    )


def validate_events(events: list[SceneEvent]) -> None:
    cached = analysis()
    cached_by_id = {event.event_id: event for event in cached.events}
    duration_ms = manifest().get("duration_ms")

    if not isinstance(duration_ms, int) or duration_ms <= 0:
        raise DemoCacheError(
            "The controlled demo manifest duration is invalid."
        )

    for event in events:
        expected = cached_by_id.get(event.event_id)

        if expected is None:
            raise DemoCacheError(
                f"Event {event.event_id} is not part of the controlled demo."
            )

        if event.timestamp_ms > duration_ms:
            raise DemoCacheError(
                f"Event {event.event_id} exceeds the controlled clip duration."
            )

        if _event_provenance(event) != _event_provenance(expected):
            raise DemoCacheError(
                f"Event {event.event_id} no longer matches cached evidence."
            )


def matches_story_request(request: StoryReelRequest) -> bool:
    if not available():
        return False

    try:
        return request.model_dump(mode="json") == cached_story_request().model_dump(
            mode="json"
        )
    except DemoCacheError:
        return False


def copy_clip_to(destination: Path) -> None:
    if not available():
        raise DemoCacheError("The controlled demo cache is incomplete.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(cache_path(CLIP_FILENAME), destination)


def copy_reel_to(destination: Path) -> None:
    if not available():
        raise DemoCacheError("The controlled demo cache is incomplete.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(cache_path(REEL_FILENAME), destination)
