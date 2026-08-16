import asyncio
import logging
import os
import re
import shutil
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from time import perf_counter
from typing import Literal
from uuid import uuid4

from fastapi import (
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, ValidationError

from backend.app.analysis import (
    SceneAnalysisError,
    analyze_video,
)
from backend.app.color_lab import (
    ColorSimulationError,
    simulate_object_colors,
)
from backend.app.contracts import (
    ColorSimulationRequest,
    ColorSimulationResponse,
    SceneAnalysisResponse,
    StoryJobCreateResponse,
    StoryJobStatusResponse,
    StoryReelRequest,
    VisibilityAnalysisResponse,
    VisibilityScoreRequest,
)
from backend.app.job_store import JobStore
from backend.app.media import (
    ALLOWED_VIDEO_TYPES,
    MediaValidationError,
    normalize_video,
    probe_duration_ms,
    save_upload,
)
from backend.app.rate_limit import SlidingWindowRateLimiter
from backend.app.settings import settings
from backend.app.story_jobs import StoryJobManager
from backend.app.visibility import (
    VisibilityScoringError,
    score_visibility_events,
)


class AnalyzeVideoResponse(BaseModel):
    analysis: SceneAnalysisResponse
    source: Literal["gemini", "demo"]


logger = logging.getLogger("uvicorn.error")


job_store = JobStore(settings.job_database)

story_job_manager = StoryJobManager(
    job_store,
    settings.jobs_directory,
)

story_job_limiter = SlidingWindowRateLimiter(
    settings.story_jobs_per_hour,
    60 * 60,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.media_directory.mkdir(
        parents=True,
        exist_ok=True,
    )
    settings.jobs_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    await story_job_manager.start()

    try:
        yield
    finally:
        await story_job_manager.stop()


app = FastAPI(
    title="PawSpective API",
    version="0.7.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=[
        "Content-Type",
        "X-Request-ID",
    ],
    expose_headers=[
        "X-PawSpective-Story-Source",
        "X-Request-ID",
        "Retry-After",
    ],
)


@app.middleware("http")
async def add_request_context(
    request: Request,
    call_next,
):
    supplied_request_id = request.headers.get(
        "X-Request-ID",
        "",
    )

    request_id = re.sub(
        r"[^a-zA-Z0-9._-]+",
        "",
        supplied_request_id,
    )[:64]

    if not request_id:
        request_id = uuid4().hex[:16]

    started_at = perf_counter()

    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            (
                "Unhandled API error "
                "request_id=%s path=%s"
            ),
            request_id,
            request.url.path,
        )
        raise

    elapsed = perf_counter() - started_at

    response.headers["X-Request-ID"] = request_id
    response.headers[
        "X-Content-Type-Options"
    ] = "nosniff"
    response.headers[
        "Referrer-Policy"
    ] = "no-referrer"
    response.headers[
        "X-Frame-Options"
    ] = "DENY"

    logger.info(
        (
            "request_id=%s method=%s path=%s "
            "status=%s elapsed_seconds=%.3f"
        ),
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        elapsed,
    )

    return response


@app.get("/api/v1/health")
def health() -> dict[str, str | bool]:
    return {
        "status": "ok",
        "demo_mode": settings.demo_mode,
        "model": settings.gemini_model,
    }


@app.get("/api/v1/health/live")
def liveness() -> dict[str, str]:
    return {
        "status": "alive",
    }


@app.get("/api/v1/health/ready")
def readiness() -> dict[str, object]:
    problems: list[str] = []

    if shutil.which("ffmpeg") is None:
        problems.append(
            "FFmpeg is unavailable",
        )

    if shutil.which("ffprobe") is None:
        problems.append(
            "FFprobe is unavailable",
        )

    if not settings.demo_mode:
        if not settings.gemini_api_key:
            problems.append(
                "Gemini configuration is missing",
            )

        if not settings.elevenlabs_api_key:
            problems.append(
                "ElevenLabs configuration is missing",
            )

        if not settings.elevenlabs_dog_voice_id:
            problems.append(
                "ElevenLabs voice configuration is missing",
            )

    for directory in (
        settings.media_directory,
        settings.jobs_directory,
    ):
        test_path: Path | None = None

        try:
            directory.mkdir(
                parents=True,
                exist_ok=True,
            )

            if not os.access(directory, os.W_OK):
                raise OSError(
                    "Directory is not writable",
                )

            test_path = directory / (
                f".readiness-{uuid4().hex}.tmp"
            )

            test_path.write_text(
                "ok",
                encoding="utf-8",
            )

        except OSError:
            problems.append(
                f"{directory} is not writable",
            )

        finally:
            if test_path is not None:
                test_path.unlink(
                    missing_ok=True,
                )

    if problems:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "not_ready",
                "problems": problems,
            },
        )

    return {
        "status": "ready",
        "demo_mode": settings.demo_mode,
        "max_concurrent_story_jobs": (
            settings.max_concurrent_story_jobs
        ),
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
            source_path = (
                temporary_path / f"source{extension}"
            )
            normalized_path = (
                temporary_path / "normalized.mp4"
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
            detail=(
                "Scene analysis is temporarily unavailable."
            ),
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
        request = (
            VisibilityScoreRequest.model_validate_json(
                payload,
            )
        )
    except ValidationError as error:
        raise HTTPException(
            status_code=422,
            detail=(
                "The corrected event payload is invalid."
            ),
        ) from error

    extension = ALLOWED_VIDEO_TYPES[content_type]

    try:
        with tempfile.TemporaryDirectory(
            prefix="pawspective-visibility-",
            dir=settings.media_directory,
        ) as temporary_directory:
            temporary_path = Path(temporary_directory)
            source_path = (
                temporary_path / f"source{extension}"
            )
            normalized_path = (
                temporary_path / "normalized.mp4"
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


@app.post(
    "/api/v1/simulate-object-colors",
    response_model=ColorSimulationResponse,
)
async def simulate_uploaded_object_colors(
    file: UploadFile = File(...),
    payload: str = Form(...),
) -> ColorSimulationResponse:
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
        simulation_request = ColorSimulationRequest.model_validate_json(payload)
    except ValidationError as error:
        raise HTTPException(
            status_code=422,
            detail="The color simulation payload is invalid.",
        ) from error

    extension = ALLOWED_VIDEO_TYPES[content_type]

    try:
        with tempfile.TemporaryDirectory(
            prefix="pawspective-color-lab-",
            dir=settings.media_directory,
        ) as temporary_directory:
            temporary_path = Path(temporary_directory)
            source_path = temporary_path / f"source{extension}"
            normalized_path = temporary_path / "normalized.mp4"

            await save_upload(file, source_path, settings.max_upload_bytes)
            duration_ms = await asyncio.to_thread(
                probe_duration_ms,
                source_path,
            )

            if duration_ms < 5_000:
                raise MediaValidationError("Record at least five seconds.")

            maximum_duration_ms = settings.max_video_duration_seconds * 1000

            if duration_ms > maximum_duration_ms:
                raise MediaValidationError(
                    "The maximum accepted duration is "
                    f"{settings.max_video_duration_seconds} seconds."
                )

            await asyncio.to_thread(
                normalize_video,
                source_path,
                normalized_path,
            )

            return await asyncio.to_thread(
                simulate_object_colors,
                normalized_path,
                simulation_request.event,
                duration_ms,
            )
    except (MediaValidationError, ColorSimulationError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post(
    "/api/v1/story-jobs",
    response_model=StoryJobCreateResponse,
    status_code=202,
)
async def create_story_job(
    request: Request,
    file: UploadFile = File(...),
    payload: str = Form(...),
) -> StoryJobCreateResponse:
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
        story_request = (
            StoryReelRequest.model_validate_json(
                payload,
            )
        )
    except ValidationError as error:
        raise HTTPException(
            status_code=422,
            detail="The Story Reel payload is invalid.",
        ) from error

    client_key = (
        request.client.host
        if request.client
        else "unknown"
    )

    retry_after = story_job_limiter.retry_after(
        client_key,
    )

    if retry_after:
        raise HTTPException(
            status_code=429,
            detail=(
                "The Story Reel limit has been reached. "
                "Please wait before trying again."
            ),
            headers={
                "Retry-After": str(retry_after),
            },
        )

    story_job_manager.cleanup_expired()

    job_id = uuid4().hex
    job_directory = story_job_manager.job_directory(
        job_id,
    )

    job_directory.mkdir(
        parents=True,
        exist_ok=False,
    )

    extension = ALLOWED_VIDEO_TYPES[content_type]
    source_path = (
        job_directory / f"source{extension}"
    )

    safe_name = re.sub(
        r"[^a-zA-Z0-9_-]+",
        "-",
        story_request.profile.dog_name,
    ).strip("-") or "dog"

    filename = (
        f"{safe_name}-pawspective-reel.mp4"
    )

    try:
        await save_upload(
            file,
            source_path,
            settings.max_upload_bytes,
        )

        job_store.create(
            job_id,
            filename,
        )

        story_job_manager.enqueue(
            job_id,
            source_path,
            story_request,
        )

    except MediaValidationError as error:
        job_store.delete(job_id)

        shutil.rmtree(
            job_directory,
            ignore_errors=True,
        )

        raise HTTPException(
            status_code=422,
            detail=str(error),
        ) from error

    except Exception:
        job_store.delete(job_id)

        shutil.rmtree(
            job_directory,
            ignore_errors=True,
        )

        raise

    return StoryJobCreateResponse(
        job_id=job_id,
        status="queued",
        status_url=(
            f"/api/v1/story-jobs/{job_id}"
        ),
    )


@app.get(
    "/api/v1/story-jobs/{job_id}",
    response_model=StoryJobStatusResponse,
)
def get_story_job(
    job_id: str,
) -> StoryJobStatusResponse:
    if not re.fullmatch(
        r"[a-f0-9]{32}",
        job_id,
    ):
        raise HTTPException(
            status_code=404,
            detail="Story job not found.",
        )

    story_job_manager.cleanup_expired()

    record = job_store.get(job_id)

    if record is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Story job not found or expired."
            ),
        )

    download_url = (
        (
            f"/api/v1/story-jobs/"
            f"{job_id}/download"
        )
        if record.status == "completed"
        else None
    )

    return StoryJobStatusResponse(
        job_id=record.job_id,
        status=record.status,
        progress=record.progress,
        error=record.error,
        story_source=record.story_source,
        download_url=download_url,
    )


@app.get(
    "/api/v1/story-jobs/{job_id}/download",
)
def download_story_job(
    job_id: str,
) -> FileResponse:
    if not re.fullmatch(
        r"[a-f0-9]{32}",
        job_id,
    ):
        raise HTTPException(
            status_code=404,
            detail="Story job not found.",
        )

    story_job_manager.cleanup_expired()

    record = job_store.get(job_id)

    if (
        record is None
        or record.status != "completed"
    ):
        raise HTTPException(
            status_code=404,
            detail=(
                "The Story Reel is not available."
            ),
        )

    output_path = (
        story_job_manager.job_directory(job_id)
        / "pawspective-reel.mp4"
    )

    if not output_path.exists():
        raise HTTPException(
            status_code=410,
            detail="The Story Reel has expired.",
        )

    return FileResponse(
        output_path,
        media_type="video/mp4",
        filename=record.filename,
        headers={
            "Cache-Control": "no-store",
            "X-PawSpective-Story-Source": (
                record.story_source or "template"
            ),
        },
    )
