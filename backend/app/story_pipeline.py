from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from backend.app.contracts import StoryReelRequest
from backend.app import demo_cache
from backend.app.demo_cache import DemoCacheError
from backend.app.media import (
    MediaValidationError,
    normalize_video,
    probe_duration_ms,
)
from backend.app.settings import settings
from backend.app.story import (
    StoryGenerationError,
    StorySource,
    generate_story,
)
from backend.app.story_render import (
    StoryRenderError,
    render_story_reel,
)
from backend.app.voice import (
    VoiceGenerationError,
    synthesize_narration,
)


ProgressCallback = Callable[[int], None]


@dataclass(frozen=True)
class StoryPipelineResult:
    output_path: Path
    story_source: StorySource


def run_story_pipeline(
    source_path: Path,
    request: StoryReelRequest,
    work_directory: Path,
    progress: ProgressCallback,
) -> StoryPipelineResult:
    normalized_path = (
        work_directory / "normalized.mp4"
    )
    narration_path = (
        work_directory / "narration.mp3"
    )
    output_path = (
        work_directory / "pawspective-reel.mp4"
    )

    progress(10)

    duration_ms = probe_duration_ms(source_path)

    if duration_ms < 5_000:
        raise MediaValidationError(
            "Record at least five seconds.",
        )

    maximum_duration_ms = (
        settings.max_video_duration_seconds * 1000
    )

    if duration_ms > maximum_duration_ms:
        raise MediaValidationError(
            "The maximum accepted duration is "
            f"{settings.max_video_duration_seconds} seconds.",
        )

    invalid_events = [
        event.event_id
        for event in request.events
        if event.timestamp_ms > duration_ms
    ]

    if invalid_events:
        raise MediaValidationError(
            "Story event timestamps exceed the video duration.",
        )

    if (
        request.analysis_source == "controlled_demo"
        and demo_cache.matches_story_request(request)
    ):
        demo_cache.require_matching_clip(source_path)
        demo_cache.validate_events(request.events)
        demo_cache.copy_reel_to(output_path)
        progress(95)

        return StoryPipelineResult(
            output_path=output_path,
            story_source="demo_cache",
        )

    normalize_video(
        source_path,
        normalized_path,
    )
    progress(30)

    story, story_source = generate_story(request)
    progress(50)

    synthesize_narration(
        story.narration_text,
        narration_path,
    )
    progress(65)

    render_story_reel(
        normalized_path,
        narration_path,
        request,
        story,
        output_path,
        duration_ms,
    )
    progress(95)

    if not output_path.exists():
        raise StoryRenderError(
            "The Story Reel output was not created.",
        )

    return StoryPipelineResult(
        output_path=output_path,
        story_source=story_source,
    )


PIPELINE_ERRORS = (
    DemoCacheError,
    MediaValidationError,
    StoryGenerationError,
    VoiceGenerationError,
    StoryRenderError,
)
