import base64
import json
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

AnalysisSource = Literal["gemini", "demo"]


class SceneAnalysisError(RuntimeError):
    pass


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
) -> tuple[SceneAnalysisResponse, AnalysisSource]:
    if settings.demo_mode:
        return (
            load_demo_analysis(
                duration_ms,
                "Demo mode is enabled; cached detections were used.",
            ),
            "demo",
        )

    if not settings.gemini_api_key:
        raise SceneAnalysisError(
            "GEMINI_API_KEY is not configured.",
        )

    client = genai.Client(
        api_key=settings.gemini_api_key,
    )

    try:
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

        interaction = client.interactions.create(
            model=settings.gemini_model,
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
                "schema": (
                    SceneAnalysisResponse.model_json_schema()
                ),
            },
        )

        if not interaction.output_text:
            raise SceneAnalysisError(
                "Gemini returned an empty response.",
            )

        payload = json.loads(interaction.output_text)

        if not isinstance(payload, dict):
            raise SceneAnalysisError(
                "Gemini returned an invalid response structure.",
            )

        # The duration measured by FFprobe is authoritative.
        payload["duration_ms"] = duration_ms

        analysis = SceneAnalysisResponse.model_validate(payload)

        return analysis, "gemini"

    except Exception as error:
        if settings.allow_demo_fallback:
            return (
                load_demo_analysis(
                    duration_ms,
                    (
                        "Gemini was unavailable; cached demo "
                        "detections were used."
                    ),
                ),
                "demo",
            )

        raise SceneAnalysisError(
            "Gemini scene analysis failed.",
        ) from error

    finally:
        client.close()