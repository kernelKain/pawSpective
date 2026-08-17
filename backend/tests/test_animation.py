from dataclasses import replace
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

import backend.app.animation as animation_module
from backend.app.animation import (
    AnimationGenerationError,
    DEFAULT_CREATIVE_DIRECTION,
    _omni_output_bytes,
    build_animation_prompt,
    extract_reference_frames,
    generate_animated_video,
    safe_creative_direction,
)
from backend.app.story import fallback_story
from backend.tests.test_story import story_request


def test_animation_prompt_uses_corrected_labels_and_dog_height() -> None:
    request = story_request()
    story = fallback_story(request)

    prompt = build_animation_prompt(request, story)

    assert "60 centimetres" in prompt
    for event in request.events:
        assert event.object_label in prompt
        assert event.visible_evidence in prompt
    assert "one continuous first-person viewpoint" in prompt
    assert "not an exact biological simulation" in prompt


def test_animation_prompt_varies_camera_height_by_profile_size() -> None:
    request = story_request()
    story = fallback_story(request)

    small = build_animation_prompt(
        request.model_copy(
            update={"profile": request.profile.model_copy(update={"size": "Small"})}
        ),
        story,
    )
    large = build_animation_prompt(
        request.model_copy(
            update={"profile": request.profile.model_copy(update={"size": "Large"})}
        ),
        story,
    )

    assert "30 centimetres" in small
    assert "60 centimetres" in large


def test_unsafe_model_creative_direction_is_replaced() -> None:
    assert (
        safe_creative_direction(
            "Show the dog from an external view because the dog thinks it smells a cat."
        )
        == DEFAULT_CREATIVE_DIRECTION
    )


def test_safe_model_creative_direction_is_normalized() -> None:
    assert safe_creative_direction(
        "  Watercolor textures\nwith warm afternoon light.  "
    ) == "Watercolor textures with warm afternoon light."


def test_extract_reference_frames_samples_start_middle_and_end(tmp_path) -> None:
    source = tmp_path / "source.mp4"
    writer = cv2.VideoWriter(
        str(source),
        cv2.VideoWriter_fourcc(*"mp4v"),
        5,
        (64, 48),
    )
    assert writer.isOpened()
    for value in range(10):
        writer.write(np.full((48, 64, 3), value * 20, dtype=np.uint8))
    writer.release()

    paths = extract_reference_frames(source, tmp_path)

    assert [path.name for path in paths] == [
        "reference-0.jpg",
        "reference-1.jpg",
        "reference-2.jpg",
    ]
    assert all(path.stat().st_size > 0 for path in paths)


@pytest.mark.parametrize(
    ("provider", "expected_source", "expected_model"),
    [
        ("gemini_omni", "gemini_omni", "omni-test-model"),
        ("veo_3_1", "veo_3_1", "veo-test-model"),
    ],
)
def test_generate_animated_video_dispatches_selected_provider(
    tmp_path,
    monkeypatch,
    provider: str,
    expected_source: str,
    expected_model: str,
) -> None:
    source = tmp_path / "source.mp4"
    destination = tmp_path / "generated.mp4"
    source.write_bytes(b"source")
    request = story_request().model_copy(update={"animation_provider": provider})
    monkeypatch.setattr(
        animation_module,
        "settings",
        replace(
            animation_module.settings,
            demo_mode=False,
            animation_enabled=True,
            gemini_api_key="configured",
            omni_video_model="omni-test-model",
            veo_video_model="veo-test-model",
        ),
    )
    references = []
    for index in range(3):
        path = tmp_path / f"frame-{index}.jpg"
        path.write_bytes(b"jpg")
        references.append(path)
    monkeypatch.setattr(
        animation_module,
        "extract_reference_frames",
        lambda *_: references,
    )

    def fake_process(function, arguments, check_cancelled, **_kwargs):
        check_cancelled()
        assert function.__name__ == (
            "_request_omni_animation" if provider == "gemini_omni" else "_request_veo_animation"
        )
        destination.write_bytes(b"generated-video")
        return expected_model

    monkeypatch.setattr(animation_module, "run_cancellable_process", fake_process)

    source_name, model = generate_animated_video(
        source,
        destination,
        "grounded prompt",
        request,
        tmp_path,
        lambda: None,
    )

    assert source_name == expected_source
    assert model == expected_model
    assert destination.read_bytes() == b"generated-video"


def test_generation_failure_removes_partial_output(tmp_path, monkeypatch) -> None:
    source = tmp_path / "source.mp4"
    destination = tmp_path / "generated.mp4"
    source.write_bytes(b"source")
    monkeypatch.setattr(
        animation_module,
        "settings",
        replace(
            animation_module.settings,
            demo_mode=False,
            animation_enabled=True,
            gemini_api_key="configured",
        ),
    )

    def fail_process(*_args, **_kwargs):
        destination.write_bytes(b"partial")
        raise TimeoutError("provider timed out")

    monkeypatch.setattr(animation_module, "run_cancellable_process", fail_process)

    with pytest.raises(AnimationGenerationError, match="generation failed"):
        generate_animated_video(
            source,
            destination,
            "grounded prompt",
            story_request(),
            tmp_path,
            lambda: None,
        )

    assert not destination.exists()


def test_omni_uri_output_uses_files_api_download(monkeypatch) -> None:
    class FakeFiles:
        def __init__(self) -> None:
            self.downloaded = None

        def get(self, *, name: str):
            assert name == "files/video-123"
            return SimpleNamespace(state="ACTIVE")

        def download(self, *, file: str) -> bytes:
            self.downloaded = file
            return b"video-bytes"

    files = FakeFiles()
    client = SimpleNamespace(files=files)
    interaction = SimpleNamespace(
        output_video=SimpleNamespace(
            data=None,
            uri="https://generativelanguage.googleapis.com/v1beta/files/video-123",
        )
    )
    monkeypatch.setattr(animation_module.time, "sleep", lambda _: None)

    output = _omni_output_bytes(interaction, client, "unused")

    assert output == b"video-bytes"
    assert files.downloaded == interaction.output_video.uri
