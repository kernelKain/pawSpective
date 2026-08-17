from shutil import copyfile

import pytest

import backend.app.story_pipeline as pipeline_module
from backend.app.contracts import StoryReelRequest
from backend.app.media import MediaValidationError
from backend.app.settings import settings
from backend.app.story import (
    StoryGenerationError,
    fallback_story,
)
from backend.app.story_pipeline import run_story_pipeline
from backend.app.story_render import StoryRenderError
from backend.app.voice import VoiceGenerationError
from backend.tests.test_story import story_request


def configure_pipeline(monkeypatch) -> None:
    def fake_render(*args, check_cancelled) -> None:
        check_cancelled()
        args[4].write_bytes(b"fake-story-mp4")

    monkeypatch.setattr(
        pipeline_module,
        "probe_duration_ms",
        lambda _: 8_000,
    )
    monkeypatch.setattr(
        pipeline_module,
        "normalize_video",
        lambda source, destination, **kwargs: copyfile(
            source,
            destination,
        ),
    )
    monkeypatch.setattr(
        pipeline_module,
        "generate_story",
        lambda request, **kwargs: (
            fallback_story(request),
            "template",
        ),
    )
    monkeypatch.setattr(
        pipeline_module,
        "synthesize_narration",
        lambda text, destination, **kwargs: destination.write_bytes(
            b"audio",
        ),
    )
    monkeypatch.setattr(
        pipeline_module,
        "render_story_reel",
        fake_render,
    )


def test_pipeline_renders_downloadable_mp4(
    tmp_path,
    monkeypatch,
) -> None:
    configure_pipeline(monkeypatch)
    source_path = tmp_path / "source.mp4"
    source_path.write_bytes(b"video")
    progress: list[int] = []

    result = run_story_pipeline(
        source_path,
        story_request(),
        tmp_path,
        progress.append,
    )

    assert result.output_path.read_bytes() == (
        b"fake-story-mp4"
    )
    assert result.story_source == "template"
    assert result.artifact_source == "live_render"
    assert result.voice_source == "elevenlabs"
    assert result.variation_id == "original"
    assert result.animation_seed == 0
    assert result.music_track_id == "sunny-paws"
    assert progress == [10, 30, 50, 65, 95]


def test_matching_controlled_request_bypasses_voice_and_rendering(
    tmp_path,
    monkeypatch,
) -> None:
    source_path = tmp_path / "source.mp4"
    source_path.write_bytes(b"verified demo")
    request = story_request().model_copy(
        update={"analysis_source": "controlled_demo"}
    )
    progress: list[int] = []

    monkeypatch.setattr(pipeline_module, "probe_duration_ms", lambda _: 8_000)
    monkeypatch.setattr(
        pipeline_module.demo_cache,
        "matches_story_request",
        lambda _: True,
    )
    monkeypatch.setattr(
        pipeline_module.demo_cache,
        "require_matching_clip",
        lambda _: None,
    )
    monkeypatch.setattr(
        pipeline_module.demo_cache,
        "validate_events",
        lambda _: None,
    )
    monkeypatch.setattr(
        pipeline_module.demo_cache,
        "copy_reel_to",
        lambda destination: destination.write_bytes(b"cached reel"),
    )
    monkeypatch.setattr(
        pipeline_module.demo_cache,
        "cached_story_request",
        lambda: request,
    )
    monkeypatch.setattr(
        pipeline_module,
        "synthesize_narration",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            VoiceGenerationError("ElevenLabs timed out")
        ),
    )

    result = run_story_pipeline(source_path, request, tmp_path, progress.append)

    assert result.story_source == "demo_cache"
    assert result.artifact_source == "controlled_demo_cache"
    assert result.voice_source == "controlled_demo_cache"
    assert result.variation_id == request.variation_id
    assert result.animation_seed == request.animation_seed
    assert result.music_track_id == "sunny-paws"
    assert result.output_path.read_bytes() == b"cached reel"
    assert progress == [10, 95]


@pytest.mark.parametrize(
    ("duration_ms", "message"),
    [
        (4_999, "at least five seconds"),
        (
            settings.max_video_duration_seconds * 1_000 + 1,
            "maximum accepted duration",
        ),
    ],
)
def test_pipeline_rejects_invalid_duration(
    tmp_path,
    monkeypatch,
    duration_ms: int,
    message: str,
) -> None:
    source_path = tmp_path / "source.mp4"
    source_path.write_bytes(b"video")
    monkeypatch.setattr(
        pipeline_module,
        "probe_duration_ms",
        lambda _: duration_ms,
    )

    with pytest.raises(
        MediaValidationError,
        match=message,
    ):
        run_story_pipeline(
            source_path,
            story_request(),
            tmp_path,
            lambda _: None,
        )


def test_pipeline_rejects_event_after_video(
    tmp_path,
    monkeypatch,
) -> None:
    configure_pipeline(monkeypatch)
    payload = story_request().model_dump(mode="json")
    payload["events"][0]["timestamp_ms"] = 8_001
    request = StoryReelRequest.model_validate(payload)
    source_path = tmp_path / "source.mp4"
    source_path.write_bytes(b"video")

    with pytest.raises(
        MediaValidationError,
        match="timestamps exceed",
    ):
        run_story_pipeline(
            source_path,
            request,
            tmp_path,
            lambda _: None,
        )


@pytest.mark.parametrize(
    ("dependency", "error"),
    [
        (
            "generate_story",
            StoryGenerationError("Gemini timed out"),
        ),
        (
            "synthesize_narration",
            VoiceGenerationError("ElevenLabs timed out"),
        ),
        (
            "render_story_reel",
            StoryRenderError("FFmpeg failed"),
        ),
    ],
)
def test_pipeline_preserves_dependency_failures(
    tmp_path,
    monkeypatch,
    dependency: str,
    error: Exception,
) -> None:
    configure_pipeline(monkeypatch)
    source_path = tmp_path / "source.mp4"
    source_path.write_bytes(b"video")

    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(
        pipeline_module,
        dependency,
        fail,
    )

    with pytest.raises(type(error), match=str(error)):
        run_story_pipeline(
            source_path,
            story_request(),
            tmp_path,
            lambda _: None,
        )


def test_pipeline_requires_rendered_output(
    tmp_path,
    monkeypatch,
) -> None:
    def skip_output(*args, check_cancelled) -> None:
        check_cancelled()

    configure_pipeline(monkeypatch)
    monkeypatch.setattr(
        pipeline_module,
        "render_story_reel",
        skip_output,
    )
    source_path = tmp_path / "source.mp4"
    source_path.write_bytes(b"video")

    with pytest.raises(
        StoryRenderError,
        match="output was not created",
    ):
        run_story_pipeline(
            source_path,
            story_request(),
            tmp_path,
            lambda _: None,
        )


def test_modified_controlled_request_never_receives_original_cached_reel(
    tmp_path,
    monkeypatch,
) -> None:
    configure_pipeline(monkeypatch)
    source_path = tmp_path / "source.mp4"
    source_path.write_bytes(b"verified demo")
    request = story_request().model_copy(
        update={
            "analysis_source": "controlled_demo",
            "variation_id": "new-variation",
            "animation_seed": 2,
        }
    )
    copied = False

    monkeypatch.setattr(
        pipeline_module.demo_cache,
        "matches_story_request",
        lambda _: False,
    )
    monkeypatch.setattr(
        pipeline_module.demo_cache,
        "require_matching_clip",
        lambda _: None,
    )
    monkeypatch.setattr(
        pipeline_module,
        "generate_story",
        lambda _, **kwargs: (_ for _ in ()).throw(
            StoryGenerationError("offline")
        ),
    )

    def copy_reel(_destination) -> None:
        nonlocal copied
        copied = True

    monkeypatch.setattr(pipeline_module.demo_cache, "copy_reel_to", copy_reel)

    with pytest.raises(pipeline_module.DemoCacheError, match="does not match"):
        run_story_pipeline(source_path, request, tmp_path, lambda _: None)

    assert not copied
