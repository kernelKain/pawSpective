import time
from dataclasses import replace

import pytest

from backend.app.cancellable import run_cancellable_process
from backend.app.contracts import StoryReelRequest


class CancelledForTest(RuntimeError):
    pass


def blocking_story_provider(
    api_key: str,
    model: str,
    prompt: str,
    schema: dict[str, object],
) -> str:
    del api_key, model, prompt, schema
    time.sleep(10)
    return "unreachable"


def blocking_narration_provider(
    api_key: str,
    voice_id: str,
    model_id: str,
    text: str,
) -> bytes:
    del api_key, voice_id, model_id, text
    time.sleep(10)
    return b"unreachable"


def provider_story_request() -> StoryReelRequest:
    return StoryReelRequest.model_validate(
        {
            "analysis_source": "gemini",
            "style": "nature_documentary",
            "profile": {
                "owner_name": "Alex",
                "dog_name": "Scout",
                "breed": "Mixed breed",
                "age": "Adult",
                "size": "Medium",
                "personality_tags": ["Curious"],
                "favorite_interest": "Ball",
            },
            "events": [
                {
                    "event_id": "ball",
                    "timestamp_ms": 1_000,
                    "object_label": "blue ball",
                    "category": "toy",
                    "bounding_box": {
                        "x_min": 0.2,
                        "y_min": 0.3,
                        "x_max": 0.5,
                        "y_max": 0.7,
                    },
                    "confidence": 0.93,
                    "visible_evidence": "A blue ball is visible.",
                    "motion_level": "medium",
                }
            ],
            "scores": [
                {
                    "event_id": "ball",
                    "identification_confidence": 0.93,
                    "human_contrast_score": 72,
                    "dog_contrast_score": 86,
                    "contrast_change": 14,
                    "motion_score": 67,
                    "apparent_size_score": 60,
                    "profile_relevance_score": 100,
                    "salience_score": 75,
                    "salience_level": "high",
                    "human_object_color": "#2478D0",
                    "human_background_color": "#3B7A3A",
                    "dog_object_color": "#357DC4",
                    "dog_background_color": "#77743B",
                    "explanation": "The ball remains visible.",
                    "why": ["Contrast remains high."],
                }
            ],
            "featured_event_id": "ball",
        }
    )


def test_cancellation_terminates_blocking_provider_process() -> None:
    started = time.monotonic()

    def check_cancelled() -> None:
        if time.monotonic() - started >= 0.2:
            raise CancelledForTest("cancelled")

    with pytest.raises(CancelledForTest, match="cancelled"):
        run_cancellable_process(
            time.sleep,
            (10,),
            check_cancelled,
            timeout_seconds=15,
        )

    assert time.monotonic() - started < 3


def test_generate_story_routes_gemini_through_cancellable_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import backend.app.story as story_module

    monkeypatch.setattr(
        story_module,
        "settings",
        replace(
            story_module.settings,
            demo_mode=False,
            allow_demo_fallback=True,
            gemini_api_key="configured-test-key",
        ),
    )
    observed: dict[str, object] = {}

    def check_cancelled() -> None:
        raise CancelledForTest("cancelled")

    def cancelling_runner(
        target,
        arguments,
        cancellation_check,
        *,
        timeout_seconds,
    ):
        observed.update(
            target=target,
            arguments=arguments,
            timeout_seconds=timeout_seconds,
        )
        cancellation_check()
        raise AssertionError("Cancellation check should have raised")

    monkeypatch.setattr(
        story_module,
        "run_cancellable_process",
        cancelling_runner,
    )
    started = time.monotonic()

    with pytest.raises(CancelledForTest, match="cancelled"):
        story_module.generate_story(
            provider_story_request(),
            check_cancelled=check_cancelled,
        )

    assert observed["target"] is story_module._request_gemini_story
    assert observed["timeout_seconds"] == 60
    assert observed["arguments"][:2] == (
        "configured-test-key",
        story_module.settings.gemini_model,
    )
    assert time.monotonic() - started < 1


def test_synthesize_narration_routes_elevenlabs_through_cancellable_process(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    import backend.app.voice as voice_module

    monkeypatch.setattr(
        voice_module,
        "settings",
        replace(
            voice_module.settings,
            elevenlabs_api_key="configured-test-key",
            elevenlabs_dog_voice_id="voice-123",
            elevenlabs_model_id="eleven_flash_v2_5",
        ),
    )
    destination = tmp_path / "narration.mp3"
    destination.write_bytes(b"stale artifact")
    observed: dict[str, object] = {}

    def check_cancelled() -> None:
        raise CancelledForTest("cancelled")

    def cancelling_runner(
        target,
        arguments,
        cancellation_check,
        *,
        timeout_seconds,
    ):
        observed.update(
            target=target,
            arguments=arguments,
            timeout_seconds=timeout_seconds,
        )
        cancellation_check()
        raise AssertionError("Cancellation check should have raised")

    monkeypatch.setattr(
        voice_module,
        "run_cancellable_process",
        cancelling_runner,
    )
    started = time.monotonic()

    with pytest.raises(CancelledForTest, match="cancelled"):
        voice_module.synthesize_narration(
            "Safe fictional narration.",
            destination,
            check_cancelled=check_cancelled,
        )

    assert observed["target"] is voice_module._request_narration
    assert observed["arguments"] == (
        "configured-test-key",
        "voice-123",
        "eleven_flash_v2_5",
        "Safe fictional narration.",
    )
    assert observed["timeout_seconds"] == 50
    assert not destination.exists()
    assert time.monotonic() - started < 1


def test_generate_story_returns_cancellable_provider_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import backend.app.story as story_module

    monkeypatch.setattr(
        story_module,
        "settings",
        replace(
            story_module.settings,
            demo_mode=False,
            allow_demo_fallback=False,
            gemini_api_key="configured-test-key",
        ),
    )
    request = provider_story_request()
    provider_result = story_module.fallback_story(request).model_dump_json()
    observed: dict[str, object] = {}

    def returning_runner(
        target,
        arguments,
        cancellation_check,
        *,
        timeout_seconds,
    ):
        cancellation_check()
        observed.update(
            target=target,
            arguments=arguments,
            timeout_seconds=timeout_seconds,
        )
        return provider_result

    monkeypatch.setattr(
        story_module,
        "run_cancellable_process",
        returning_runner,
    )

    story, source = story_module.generate_story(
        request,
        check_cancelled=lambda: None,
    )

    assert source == "gemini"
    assert story.narration_text == story_module.fallback_story(
        request
    ).narration_text
    assert observed["target"] is story_module._request_gemini_story
    assert observed["timeout_seconds"] == 60
    assert "Scout" in observed["arguments"][2]
    assert "Alex" not in observed["arguments"][2]


def test_synthesize_narration_writes_cancellable_provider_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    import backend.app.voice as voice_module

    monkeypatch.setattr(
        voice_module,
        "settings",
        replace(
            voice_module.settings,
            elevenlabs_api_key="configured-test-key",
            elevenlabs_dog_voice_id="voice-123",
            elevenlabs_model_id="eleven_flash_v2_5",
        ),
    )
    audio = b"ID3" + b"a" * 2_000
    observed: dict[str, object] = {}

    def returning_runner(
        target,
        arguments,
        cancellation_check,
        *,
        timeout_seconds,
    ):
        cancellation_check()
        observed.update(
            target=target,
            arguments=arguments,
            timeout_seconds=timeout_seconds,
        )
        return audio

    monkeypatch.setattr(
        voice_module,
        "run_cancellable_process",
        returning_runner,
    )
    destination = tmp_path / "narration.mp3"

    voice_module.synthesize_narration(
        "Safe fictional narration.",
        destination,
        check_cancelled=lambda: None,
    )

    assert destination.read_bytes() == audio
    assert observed["target"] is voice_module._request_narration
    assert observed["timeout_seconds"] == 50


def test_generate_story_real_process_cancellation_is_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import backend.app.story as story_module

    monkeypatch.setattr(
        story_module,
        "settings",
        replace(
            story_module.settings,
            demo_mode=False,
            allow_demo_fallback=True,
            gemini_api_key="configured-test-key",
        ),
    )
    monkeypatch.setattr(
        story_module,
        "_request_gemini_story",
        blocking_story_provider,
    )
    started = time.monotonic()

    def check_cancelled() -> None:
        if time.monotonic() - started >= 0.2:
            raise CancelledForTest("cancelled")

    with pytest.raises(CancelledForTest, match="cancelled"):
        story_module.generate_story(
            provider_story_request(),
            check_cancelled=check_cancelled,
        )

    assert time.monotonic() - started < 3


def test_synthesize_narration_real_process_cancellation_cleans_artifact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    import backend.app.voice as voice_module

    monkeypatch.setattr(
        voice_module,
        "settings",
        replace(
            voice_module.settings,
            elevenlabs_api_key="configured-test-key",
            elevenlabs_dog_voice_id="voice-123",
            elevenlabs_model_id="eleven_flash_v2_5",
        ),
    )
    monkeypatch.setattr(
        voice_module,
        "_request_narration",
        blocking_narration_provider,
    )
    destination = tmp_path / "narration.mp3"
    destination.write_bytes(b"stale artifact")
    started = time.monotonic()

    def check_cancelled() -> None:
        if time.monotonic() - started >= 0.2:
            raise CancelledForTest("cancelled")

    with pytest.raises(CancelledForTest, match="cancelled"):
        voice_module.synthesize_narration(
            "Safe fictional narration.",
            destination,
            check_cancelled=check_cancelled,
        )

    assert not destination.exists()
    assert time.monotonic() - started < 3
