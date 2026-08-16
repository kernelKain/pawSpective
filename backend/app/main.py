import asyncio
import logging
import re
import tempfile
from pathlib import Path
from time import perf_counter
from typing import Literal

from fastapi import (
    FastAPI,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ValidationError

from backend.app.analysis import (
    SceneAnalysisError,
    analyze_video,
)
from backend.app.contracts import (
    SceneAnalysisResponse,
    StoryReelRequest,
    VisibilityAnalysisResponse,
    VisibilityScoreRequest,
)
from backend.app.media import (
    ALLOWED_VIDEO_TYPES,
    MediaValidationError,
    normalize_video,
    probe_duration_ms,
    save_upload,
)
from backend.app.settings import settings
from backend.app.story import (
    StoryGenerationError,
    generate_story,
)
from backend.app.story_render import (
    StoryRenderError,
    render_story_reel,
)
from backend.app.visibility import (
    VisibilityScoringError,
    score_visibility_events,
)
from backend.app.voice import (
    VoiceGenerationError,
    synthesize_narration,
)


class AnalyzeVideoResponse(BaseModel):
    analysis: SceneAnalysisResponse
    source: Literal["gemini", "demo"]


logger = logging.getLogger("uvicorn.error")


app = FastAPI(
    title="PawSpective API",
    version="0.5.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
    expose_headers=["X-PawSpective-Story-Source"],
)

settings.media_directory.mkdir(
    parents=True,
    exist_ok=True,
)


@app.get("/api/v1/health")
def health() -> dict[str, str | bool]:
    return {
        "status": "ok",
        "demo_mode": settings.demo_mode,
        "model": settings.gemini_model,
    }


@app.post(
    "/api/v1/analyze-video",
    response_model=AnalyzeVideoResponse,
)
async def analyze_uploaded_video(
    file: UploadFile = File(...),
) -> AnalyzeVideoResponse:
    content_type = file.content_type or ""

    if content_type not in ALLOWED_VIDEO_TYPES:
        raise HTTPException(
            status_code=415,
            detail=(
                "Unsupported video type. Upload MP4, WebM, "
                "QuickTime, or Matroska video."
            ),
        )

    extension = ALLOWED_VIDEO_TYPES[content_type]

    try:
        with tempfile.TemporaryDirectory(
            prefix="pawspective-",
            dir=settings.media_directory,
        ) as temporary_directory:
            temporary_path = Path(temporary_directory)
            source_path = temporary_path / f"source{extension}"
            normalized_path = temporary_path / "normalized.mp4"

            await save_upload(
                file,
                source_path,
                settings.max_upload_bytes,
            )

            duration_ms = await asyncio.to_thread(
                probe_duration_ms,
                source_path,
            )

            if duration_ms < 5_000:
                raise MediaValidationError(
                    "Record at least five seconds.",
                )

            maximum_duration_ms = (
                settings.max_video_duration_seconds * 1000
            )

            if duration_ms > maximum_duration_ms:
                raise MediaValidationError(
                    "The maximum accepted duration is "
                    f"{settings.max_video_duration_seconds} seconds.",
                )

            await asyncio.to_thread(
                normalize_video,
                source_path,
                normalized_path,
            )

            analysis_started_at = perf_counter()
            analysis, source = await asyncio.to_thread(
                analyze_video,
                normalized_path,
                duration_ms,
            )
            logger.info(
                "Gemini scene analysis completed in %.2f seconds",
                perf_counter() - analysis_started_at,
            )

            return AnalyzeVideoResponse(
                analysis=analysis,
                source=source,
            )

    except MediaValidationError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        ) from error

    except SceneAnalysisError as error:
        raise HTTPException(
            status_code=502,
            detail="Scene analysis is temporarily unavailable.",
        ) from error


@app.post(
    "/api/v1/score-visibility",
    response_model=VisibilityAnalysisResponse,
)
async def score_video_visibility(
    file: UploadFile = File(...),
    payload: str = Form(...),
) -> VisibilityAnalysisResponse:
    content_type = file.content_type or ""

    if content_type not in ALLOWED_VIDEO_TYPES:
        raise HTTPException(
            status_code=415,
            detail=(
                "Unsupported video type. Upload MP4, WebM, "
                "QuickTime, or Matroska video."
            ),
        )

    try:
        request = VisibilityScoreRequest.model_validate_json(
            payload,
        )
    except ValidationError as error:
        raise HTTPException(
            status_code=422,
            detail="The corrected event payload is invalid.",
        ) from error

    extension = ALLOWED_VIDEO_TYPES[content_type]

    try:
        with tempfile.TemporaryDirectory(
            prefix="pawspective-visibility-",
            dir=settings.media_directory,
        ) as temporary_directory:
            temporary_path = Path(temporary_directory)
            source_path = temporary_path / f"source{extension}"
            normalized_path = temporary_path / "normalized.mp4"

            await save_upload(
                file,
                source_path,
                settings.max_upload_bytes,
            )

            duration_ms = await asyncio.to_thread(
                probe_duration_ms,
                source_path,
            )

            if duration_ms < 5_000:
                raise MediaValidationError(
                    "Record at least five seconds.",
                )

            maximum_duration_ms = (
                settings.max_video_duration_seconds * 1000
            )

            if duration_ms > maximum_duration_ms:
                raise MediaValidationError(
                    "The maximum accepted duration is "
                    f"{settings.max_video_duration_seconds} seconds.",
                )

            await asyncio.to_thread(
                normalize_video,
                source_path,
                normalized_path,
            )

            return await asyncio.to_thread(
                score_visibility_events,
                normalized_path,
                request.events,
                request.favorite_interest,
                duration_ms,
            )

    except (
        MediaValidationError,
        VisibilityScoringError,
    ) as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        ) from error


@app.post("/api/v1/render-story-reel")
async def render_uploaded_story_reel(
    file: UploadFile = File(...),
    payload: str = Form(...),
) -> Response:
    content_type = file.content_type or ""

    if content_type not in ALLOWED_VIDEO_TYPES:
        raise HTTPException(
            status_code=415,
            detail=(
                "Unsupported video type. Upload MP4, WebM, "
                "QuickTime, or Matroska video."
            ),
        )

    try:
        request = StoryReelRequest.model_validate_json(
            payload,
        )
    except ValidationError as error:
        raise HTTPException(
            status_code=422,
            detail="The Story Reel payload is invalid.",
        ) from error

    extension = ALLOWED_VIDEO_TYPES[content_type]
    request_started_at = perf_counter()

    try:
        with tempfile.TemporaryDirectory(
            prefix="pawspective-story-",
            dir=settings.media_directory,
        ) as temporary_directory:
            temporary_path = Path(temporary_directory)

            source_path = (
                temporary_path / f"source{extension}"
            )
            normalized_path = (
                temporary_path / "normalized.mp4"
            )
            narration_path = (
                temporary_path / "narration.mp3"
            )
            output_path = (
                temporary_path / "pawspective-reel.mp4"
            )

            await save_upload(
                file,
                source_path,
                settings.max_upload_bytes,
            )

            duration_ms = await asyncio.to_thread(
                probe_duration_ms,
                source_path,
            )

            if duration_ms < 5_000:
                raise MediaValidationError(
                    "Record at least five seconds.",
                )

            maximum_duration_ms = (
                settings.max_video_duration_seconds * 1000
            )

            if duration_ms > maximum_duration_ms:
                raise MediaValidationError(
                    "The maximum accepted duration is "
                    f"{settings.max_video_duration_seconds} seconds.",
                )

            invalid_events = [
                event.event_id
                for event in request.events
                if event.timestamp_ms > duration_ms
            ]

            if invalid_events:
                raise MediaValidationError(
                    "Story event timestamps exceed the video duration.",
                )

            await asyncio.to_thread(
                normalize_video,
                source_path,
                normalized_path,
            )

            story_voice_started_at = perf_counter()
            story, story_source = await asyncio.to_thread(
                generate_story,
                request,
            )

            await asyncio.to_thread(
                synthesize_narration,
                story.narration_text,
                narration_path,
            )
            logger.info(
                "Story generation and narration completed in %.2f seconds",
                perf_counter() - story_voice_started_at,
            )

            composition_started_at = perf_counter()
            await asyncio.to_thread(
                render_story_reel,
                normalized_path,
                narration_path,
                request,
                story,
                output_path,
                duration_ms,
            )
            logger.info(
                "Story Reel composition completed in %.2f seconds",
                perf_counter() - composition_started_at,
            )

            reel_bytes = output_path.read_bytes()

            safe_name = re.sub(
                r"[^a-zA-Z0-9_-]+",
                "-",
                request.profile.dog_name,
            ).strip("-") or "dog"

            logger.info(
                "Complete Story Reel request completed in %.2f seconds",
                perf_counter() - request_started_at,
            )

            return Response(
                content=reel_bytes,
                media_type="video/mp4",
                headers={
                    "Content-Disposition": (
                        "attachment; filename="
                        f'"{safe_name}-pawspective-reel.mp4"'
                    ),
                    "X-PawSpective-Story-Source": (
                        story_source
                    ),
                    "Cache-Control": "no-store",
                },
            )

    except MediaValidationError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        ) from error

    except StoryGenerationError as error:
        raise HTTPException(
            status_code=502,
            detail=(
                "The grounded story could not be generated."
            ),
        ) from error

    except VoiceGenerationError as error:
        raise HTTPException(
            status_code=502,
            detail=(
                "The fictional dog voice is unavailable."
            ),
        ) from error

    except StoryRenderError as error:
        raise HTTPException(
            status_code=500,
            detail=str(error),
        ) from error
