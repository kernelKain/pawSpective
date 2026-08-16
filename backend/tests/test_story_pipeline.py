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
    monkeypatch.setattr(
        pipeline_module,
        "probe_duration_ms",
        lambda _: 8_000,
    )
    monkeypatch.setattr(
        pipeline_module,
        "normalize_video",
        lambda source, destination: copyfile(
            source,
            destination,
        ),
    )
    monkeypatch.setattr(
        pipeline_module,
        "generate_story",
        lambda request: (
            fallback_story(request),
            "template",
        ),
    )
    monkeypatch.setattr(
        pipeline_module,
        "synthesize_narration",
        lambda text, destination: destination.write_bytes(
            b"audio",
        ),
    )
    monkeypatch.setattr(
        pipeline_module,
        "render_story_reel",
        lambda *args: args[4].write_bytes(
            b"fake-story-mp4",
        ),
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
    assert progress == [10, 30, 50, 65, 95]


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
    configure_pipeline(monkeypatch)
    monkeypatch.setattr(
        pipeline_module,
        "render_story_reel",
        lambda *args: None,
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
