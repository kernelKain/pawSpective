from pathlib import Path

import httpx

from backend.app.settings import settings


class VoiceGenerationError(RuntimeError):
    pass


def synthesize_narration(
    text: str,
    destination: Path,
) -> None:
    if not settings.elevenlabs_api_key:
        raise VoiceGenerationError(
            "ELEVENLABS_API_KEY is not configured.",
        )

    if not settings.elevenlabs_dog_voice_id:
        raise VoiceGenerationError(
            "ELEVENLABS_DOG_VOICE_ID is not configured.",
        )

    url = (
        "https://api.elevenlabs.io/v1/text-to-speech/"
        f"{settings.elevenlabs_dog_voice_id}"
    )

    try:
        with httpx.Client(
            timeout=httpx.Timeout(45.0, connect=10.0),
        ) as client:
            response = client.post(
                url,
                params={
                    "output_format": "mp3_44100_128",
                },
                headers={
                    "xi-api-key": settings.elevenlabs_api_key,
                    "Content-Type": "application/json",
                    "Accept": "audio/mpeg",
                },
                json={
                    "text": text,
                    "model_id": settings.elevenlabs_model_id,
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
            raise VoiceGenerationError(
                "ElevenLabs could not generate narration.",
            )

        if len(response.content) < 1_000:
            raise VoiceGenerationError(
                "ElevenLabs returned incomplete audio.",
            )

        destination.write_bytes(response.content)

    except httpx.HTTPError as error:
        raise VoiceGenerationError(
            "ElevenLabs is temporarily unavailable.",
        ) from error