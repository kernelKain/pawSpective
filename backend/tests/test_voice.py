from dataclasses import replace

import httpx
import pytest

from backend.app.voice import (
    VoiceGenerationError,
    synthesize_narration,
)


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        content: bytes,
    ) -> None:
        self.status_code = status_code
        self.content = content


class FakeClient:
    def __init__(self, response=None, error=None) -> None:
        self.response = response
        self.error = error
        self.request = None

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        pass

    def post(self, url, **kwargs):
        self.request = (url, kwargs)

        if self.error is not None:
            raise self.error

        return self.response


def configured_settings(voice_module, **changes):
    return replace(
        voice_module.settings,
        elevenlabs_api_key="configured-test-key",
        elevenlabs_dog_voice_id="voice-123",
        elevenlabs_model_id="eleven_flash_v2_5",
        **changes,
    )


def test_missing_elevenlabs_key_is_rejected(
    monkeypatch,
    tmp_path,
) -> None:
    import backend.app.voice as voice_module

    monkeypatch.setattr(
        voice_module,
        "settings",
        replace(
            voice_module.settings,
            elevenlabs_api_key="",
            elevenlabs_dog_voice_id="voice-123",
        ),
    )

    with pytest.raises(
        VoiceGenerationError,
        match="ELEVENLABS_API_KEY",
    ):
        synthesize_narration(
            "Safe fictional narration.",
            tmp_path / "narration.mp3",
        )


def test_missing_voice_id_is_rejected(
    monkeypatch,
    tmp_path,
) -> None:
    import backend.app.voice as voice_module

    monkeypatch.setattr(
        voice_module,
        "settings",
        replace(
            voice_module.settings,
            elevenlabs_api_key="configured-test-key",
            elevenlabs_dog_voice_id="",
        ),
    )

    with pytest.raises(
        VoiceGenerationError,
        match="ELEVENLABS_DOG_VOICE_ID",
    ):
        synthesize_narration(
            "Safe fictional narration.",
            tmp_path / "narration.mp3",
        )


def test_invalid_voice_id_returns_safe_error(
    monkeypatch,
    tmp_path,
) -> None:
    import backend.app.voice as voice_module

    fake_client = FakeClient(
        response=FakeResponse(401, b'{"detail":"invalid"}'),
    )
    monkeypatch.setattr(
        voice_module,
        "settings",
        configured_settings(voice_module),
    )
    monkeypatch.setattr(
        voice_module.httpx,
        "Client",
        lambda **kwargs: fake_client,
    )

    with pytest.raises(
        VoiceGenerationError,
        match="could not generate narration",
    ):
        synthesize_narration(
            "Safe fictional narration.",
            tmp_path / "narration.mp3",
        )


def test_elevenlabs_timeout_returns_safe_error(
    monkeypatch,
    tmp_path,
) -> None:
    import backend.app.voice as voice_module

    fake_client = FakeClient(
        error=httpx.ReadTimeout("request timed out"),
    )
    monkeypatch.setattr(
        voice_module,
        "settings",
        configured_settings(voice_module),
    )
    monkeypatch.setattr(
        voice_module.httpx,
        "Client",
        lambda **kwargs: fake_client,
    )

    with pytest.raises(
        VoiceGenerationError,
        match="temporarily unavailable",
    ):
        synthesize_narration(
            "Safe fictional narration.",
            tmp_path / "narration.mp3",
        )


def test_successful_narration_is_written(
    monkeypatch,
    tmp_path,
) -> None:
    import backend.app.voice as voice_module

    audio = b"ID3" + b"a" * 2_000
    fake_client = FakeClient(
        response=FakeResponse(200, audio),
    )
    monkeypatch.setattr(
        voice_module,
        "settings",
        configured_settings(voice_module),
    )
    monkeypatch.setattr(
        voice_module.httpx,
        "Client",
        lambda **kwargs: fake_client,
    )

    destination = tmp_path / "narration.mp3"
    synthesize_narration(
        "Safe fictional narration.",
        destination,
    )

    assert destination.read_bytes() == audio
    url, request = fake_client.request
    assert url.endswith("/voice-123")
    assert request["json"]["model_id"] == "eleven_flash_v2_5"
    assert request["headers"]["xi-api-key"] == "configured-test-key"
