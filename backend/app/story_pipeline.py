from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from backend.app import demo_cache
from backend.app.animation import (
    AnimationGenerationError,
    build_animation_prompt,
    generate_animated_video,
    prepare_animation_source,
)
from backend.app.contracts import StoryReelRequest
from backend.app.demo_cache import DemoCacheError
from backend.app.media import MediaValidationError, normalize_video, probe_duration_ms
from backend.app.settings import settings
from backend.app.story import StoryGenerationError, StorySource, generate_story
from backend.app.story_render import (
    StoryRenderError,
    music_track_id,
    render_animated_story_reel,
    render_story_reel,
)
from backend.app.voice import VoiceGenerationError, synthesize_narration


ProgressCallback = Callable[[int], None]
CancellationCheck = Callable[[], None]


class StoryPipelineCancelled(RuntimeError):
    """Raised at cooperative boundaries when a Story job has been cancelled."""


@dataclass(frozen=True)
class StoryPipelineResult:
    output_path: Path
    story_source: StorySource
    artifact_source: str
    voice_source: str
    variation_id: str
    animation_seed: int
    music_track_id: str
    visual_source: str
    visual_model: str | None


def _not_cancelled() -> None:
    return None


def _copy_controlled_fallback(
    source_path: Path,
    request: StoryReelRequest,
    output_path: Path,
    progress: ProgressCallback,
    check_cancelled: CancellationCheck,
) -> StoryPipelineResult:
    check_cancelled()
    demo_cache.require_matching_clip(source_path)
    if not demo_cache.matches_story_request(request):
        raise DemoCacheError(
            "The saved controlled-demo reel does not match this Story request."
        )

    # Metadata comes from the cache-owned request, never from the request that
    # happened to trigger a fallback. This keeps the status bound to the bytes.
    cached_request = demo_cache.cached_story_request()
    demo_cache.copy_reel_to(output_path)
    check_cancelled()
    progress(95)
    return StoryPipelineResult(
        output_path=output_path,
        story_source="demo_cache",
        artifact_source="controlled_demo_cache",
        voice_source="controlled_demo_cache",
        variation_id=cached_request.variation_id,
        animation_seed=cached_request.animation_seed,
        music_track_id=music_track_id(cached_request.animation_seed),
        visual_source="controlled_demo_cache",
        visual_model=None,
    )


def run_story_pipeline(
    source_path: Path,
    request: StoryReelRequest,
    work_directory: Path,
    progress: ProgressCallback,
    check_cancelled: CancellationCheck = _not_cancelled,
) -> StoryPipelineResult:
    normalized_path = work_directory / "normalized.mp4"
    animation_input_path = work_directory / "animation-input.mp4"
    generated_animation_path = work_directory / "generated-animation.mp4"
    narration_path = work_directory / "narration.mp3"
    output_path = work_directory / "pawspective-reel.mp4"

    def report(value: int) -> None:
        check_cancelled()
        progress(value)
        check_cancelled()

    report(10)
    duration_ms = probe_duration_ms(source_path)
    check_cancelled()
    if duration_ms < 5_000:
        raise MediaValidationError("Record at least five seconds.")

    maximum_duration_ms = settings.max_video_duration_seconds * 1000
    if duration_ms > maximum_duration_ms:
        raise MediaValidationError(
            "The maximum accepted duration is "
            f"{settings.max_video_duration_seconds} seconds."
        )

    if any(event.timestamp_ms > duration_ms for event in request.events):
        raise MediaValidationError("Story event timestamps exceed the video duration.")

    if (
        request.analysis_source == "controlled_demo"
        and demo_cache.matches_story_request(request)
    ):
        return _copy_controlled_fallback(
            source_path,
            request,
            output_path,
            progress,
            check_cancelled,
        )

    try:
        check_cancelled()
        normalize_video(
            source_path,
            normalized_path,
            check_cancelled=check_cancelled,
        )
        report(25)
        story, story_source = generate_story(
            request,
            check_cancelled=check_cancelled,
        )
        report(38)
        synthesize_narration(
            story.narration_text,
            narration_path,
            check_cancelled=check_cancelled,
        )
        report(48)
        try:
            prepare_animation_source(
                normalized_path,
                animation_input_path,
                request,
                duration_ms,
            )
            prompt = build_animation_prompt(request, story)
            visual_source, visual_model = generate_animated_video(
                animation_input_path,
                generated_animation_path,
                prompt,
                request,
                work_directory,
                check_cancelled,
            )
            report(80)
            render_animated_story_reel(
                generated_animation_path,
                narration_path,
                request,
                story,
                output_path,
                check_cancelled=check_cancelled,
            )
        except (AnimationGenerationError, StoryRenderError):
            if not settings.allow_local_animation_fallback:
                raise
            visual_source = "local_animation_fallback"
            visual_model = None
            render_story_reel(
                normalized_path,
                narration_path,
                request,
                story,
                output_path,
                duration_ms,
                check_cancelled=check_cancelled,
            )
        report(95)
    except (
        MediaValidationError,
        StoryGenerationError,
        VoiceGenerationError,
        StoryRenderError,
        AnimationGenerationError,
    ):
        # Only the byte-verified cache's exact original request may use its
        # saved reel. Corrected or varied requests must fail rather than being
        # mislabeled as newly rendered bytes.
        if request.analysis_source != "controlled_demo":
            raise
        return _copy_controlled_fallback(
            source_path,
            request,
            output_path,
            progress,
            check_cancelled,
        )

    check_cancelled()
    if not output_path.exists():
        raise StoryRenderError("The Story Reel output was not created.")

    return StoryPipelineResult(
        output_path=output_path,
        story_source=story_source,
        artifact_source="live_render",
        voice_source="elevenlabs",
        variation_id=request.variation_id,
        animation_seed=request.animation_seed,
        music_track_id=music_track_id(request.animation_seed),
        visual_source=visual_source,
        visual_model=visual_model,
    )


PIPELINE_ERRORS = (
    DemoCacheError,
    MediaValidationError,
    StoryGenerationError,
    VoiceGenerationError,
    StoryRenderError,
    AnimationGenerationError,
)
