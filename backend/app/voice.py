from pathlib import Path
from typing import Callable

import httpx

from backend.app.cancellable import run_cancellable_process
from backend.app.settings import settings


class VoiceGenerationError(RuntimeError):
    pass


def _request_narration(
    api_key: str,
    voice_id: str,
    model_id: str,
    text: str,
) -> bytes:
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    with httpx.Client(timeout=httpx.Timeout(45.0, connect=10.0)) as client:
        response = client.post(
            url,
            params={"output_format": "mp3_44100_128"},
            headers={
                "xi-api-key": api_key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            json={
                "text": text,
                "model_id": model_id,
                "voice_settings": {
                    "stability": 0.55,
                    "similarity_boost": 0.75,
                    "style": 0.15,
                    "use_speaker_boost": True,
                    "speed": 1.05,
                },
            },
        )

    if response.status_code != 200:
        raise RuntimeError("Voice provider rejected the request.")
    if len(response.content) < 1_000:
        raise RuntimeError("Voice provider returned incomplete audio.")
    return response.content


def synthesize_narration(
    text: str,
    destination: Path,
    check_cancelled: Callable[[], None] | None = None,
) -> None:
    if not settings.elevenlabs_api_key:
        raise VoiceGenerationError("ELEVENLABS_API_KEY is not configured.")
    if not settings.elevenlabs_dog_voice_id:
        raise VoiceGenerationError("ELEVENLABS_DOG_VOICE_ID is not configured.")

    arguments = (
        settings.elevenlabs_api_key,
        settings.elevenlabs_dog_voice_id,
        settings.elevenlabs_model_id,
        text,
    )

    try:
        if check_cancelled is None:
            audio = _request_narration(*arguments)
        else:
            audio = run_cancellable_process(
                _request_narration,
                arguments,
                check_cancelled,
                timeout_seconds=50,
            )
        if check_cancelled is not None:
            check_cancelled()
        destination.write_bytes(audio)
    except Exception as error:
        destination.unlink(missing_ok=True)
        if check_cancelled is not None:
            check_cancelled()
        if isinstance(error, httpx.HTTPError):
            raise VoiceGenerationError(
                "ElevenLabs is temporarily unavailable."
            ) from error
        raise VoiceGenerationError("ElevenLabs could not generate narration.") from error
