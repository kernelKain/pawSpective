import base64
import json
import logging
from pathlib import Path
from typing import Literal

from google import genai

from backend.app.contracts import SceneAnalysisResponse
from backend.app.settings import settings


PROJECT_ROOT = Path(__file__).resolve().parents[2]

PROMPT_PATH = (
    Path(__file__).resolve().parent
    / "prompts"
    / "scene_analysis.txt"
)

DEMO_RESPONSE_PATH = (
    PROJECT_ROOT
    / "examples"
    / "scene-analysis.example.json"
)

AnalysisSource = Literal["gemini", "demo", "controlled_demo"]
MAXIMUM_INLINE_VIDEO_BYTES = 20 * 1024 * 1024

logger = logging.getLogger(__name__)


class SceneAnalysisError(RuntimeError):
    pass


def _is_quota_error(error: Exception) -> bool:
    status = getattr(error, "status_code", None) or getattr(error, "code", None)
    message = str(error).casefold()
    return status == 429 or any(
        marker in message
        for marker in (
            "quota exceeded",
            "too_many_requests",
            "error code: 429",
        )
    )


def _request_analysis(
    client: genai.Client,
    model: str,
    encoded_video: str,
    prompt: str,
    duration_ms: int,
) -> SceneAnalysisResponse:
    interaction = client.interactions.create(
        model=model,
        store=False,
        input=[
            {
                "type": "video",
                "data": encoded_video,
                "mime_type": "video/mp4",
            },
            {
                "type": "text",
                "text": prompt,
            },
        ],
        response_format={
            "type": "text",
            "mime_type": "application/json",
            "schema": SceneAnalysisResponse.model_json_schema(),
        },
    )
    if not interaction.output_text:
        raise SceneAnalysisError("Gemini returned an empty response.")

    payload = json.loads(interaction.output_text)
    if not isinstance(payload, dict):
        raise SceneAnalysisError("Gemini returned an invalid response structure.")

    payload["duration_ms"] = duration_ms
    return SceneAnalysisResponse.model_validate(payload)


def load_demo_analysis(
    duration_ms: int,
    warning: str | None = None,
) -> SceneAnalysisResponse:
    payload = json.loads(
        DEMO_RESPONSE_PATH.read_text(encoding="utf-8"),
    )

    payload["duration_ms"] = duration_ms

    for event in payload["events"]:
        event["timestamp_ms"] = min(
            event["timestamp_ms"],
            max(0, duration_ms - 1),
        )

    if warning:
        payload.setdefault("warnings", []).append(warning)

    return SceneAnalysisResponse.model_validate(payload)


def analyze_video(
    video_path: Path,
    duration_ms: int,
    controlled_fallback: SceneAnalysisResponse | None = None,
) -> tuple[SceneAnalysisResponse, AnalysisSource]:
    if settings.demo_mode:
        if controlled_fallback is not None:
            controlled_fallback.warnings.append(
                "Demo mode is enabled; the verified controlled-demo analysis was used."
            )
            return controlled_fallback, "controlled_demo"

        return (
            load_demo_analysis(
                duration_ms,
                "Demo mode is enabled; cached detections were used.",
            ),
            "demo",
        )

    client = None

    try:
        if not settings.gemini_api_key:
            raise SceneAnalysisError(
                "GEMINI_API_KEY is not configured.",
            )

        video_size = video_path.stat().st_size

        if video_size > MAXIMUM_INLINE_VIDEO_BYTES:
            raise SceneAnalysisError(
                "The normalized video exceeds Gemini's inline limit.",
            )

        client = genai.Client(
            api_key=settings.gemini_api_key,
        )

        prompt_template = PROMPT_PATH.read_text(
            encoding="utf-8",
        )

        prompt = prompt_template.replace(
            "{{DURATION_MS}}",
            str(duration_ms),
        )

        encoded_video = base64.b64encode(
            video_path.read_bytes(),
        ).decode("ascii")

        models = [settings.gemini_model]
        fallback_model = settings.gemini_analysis_fallback_model
        if fallback_model and fallback_model not in models:
            models.append(fallback_model)

        for index, model in enumerate(models):
            try:
                analysis = _request_analysis(
                    client,
                    model,
                    encoded_video,
                    prompt,
                    duration_ms,
                )
                if index > 0:
                    analysis.warnings.append(
                        "The primary Gemini quota was exhausted; scene analysis "
                        f"used the configured fallback model {model}."
                    )
                return analysis, "gemini"
            except Exception as error:
                if index == 0 and len(models) > 1 and _is_quota_error(error):
                    logger.warning(
                        "Gemini scene analysis quota exhausted for %s; trying %s",
                        model,
                        models[index + 1],
                    )
                    continue
                logger.exception("Gemini scene analysis failed for model %s", model)
                raise

    except Exception as error:
        quota_exhausted = _is_quota_error(error)
        logger.exception("Gemini scene analysis failed")

        if controlled_fallback is not None:
            controlled_fallback.warnings.append(
                "Gemini request quota is temporarily exhausted; the verified "
                "controlled-demo analysis was used."
                if quota_exhausted
                else "Gemini was unavailable; the verified controlled-demo analysis was used."
            )
            return controlled_fallback, "controlled_demo"

        if settings.allow_demo_fallback:
            return (
                load_demo_analysis(
                    duration_ms,
                    (
                        "Gemini request quota is temporarily exhausted; cached "
                        "demo detections were used. Wait for quota reset or enable billing."
                        if quota_exhausted
                        else "Gemini was unavailable; cached demo detections were used."
                    ),
                ),
                "demo",
            )

        raise SceneAnalysisError(
            "Gemini scene analysis failed.",
        ) from error

    finally:
        if client is not None:
            client.close()
