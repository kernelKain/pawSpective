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

from backend.app import demo_cache
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
    SceneEvent,
    StoryJobCreateResponse,
    StoryJobStatusResponse,
    StoryProfile,
    StoryReelRequest,
    VisibilityAnalysisResponse,
    VisibilityScoreRequest,
)
from backend.app.demo_cache import DemoCacheError
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
from backend.app.story_render import music_track_id
from backend.app.visibility import (
    VisibilityScoringError,
    score_visibility_events,
)
from backend.app.video_quality import (
    VideoQualityError,
    assess_video_quality,
)


class AnalyzeVideoResponse(BaseModel):
    analysis: SceneAnalysisResponse
    source: Literal["gemini", "demo", "controlled_demo"]


class ControlledDemoStatus(BaseModel):
    available: bool
    duration_ms: int | None = None
    clip_url: str | None = None
    profile: StoryProfile | None = None


DEMO_PROFILE_PATH = Path(__file__).resolve().parents[2] / "demo-profile.json"


def load_demo_profile() -> StoryProfile | None:
    try:
        return StoryProfile.model_validate_json(
            DEMO_PROFILE_PATH.read_text(encoding="utf-8")
        )
    except (OSError, ValidationError):
        return None


def prepare_video_for_source(
    source_path: Path,
    normalized_path: Path,
    analysis_source: str,
    events: list[SceneEvent],
) -> None:
    if analysis_source == "controlled_demo":
        demo_cache.require_matching_clip(source_path)
        demo_cache.validate_events(events)
        demo_cache.copy_clip_to(normalized_path)
        return

    normalize_video(source_path, normalized_path)


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
    version="0.8.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
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


@app.get(
    "/api/v1/demo/status",
    response_model=ControlledDemoStatus,
)
def controlled_demo_status() -> ControlledDemoStatus:
    if not demo_cache.available():
        return ControlledDemoStatus(available=False)

    cache_manifest = demo_cache.manifest()
    duration_ms = cache_manifest.get("duration_ms")

    return ControlledDemoStatus(
        available=True,
        duration_ms=duration_ms if isinstance(duration_ms, int) else None,
        clip_url="/api/v1/demo/clip",
        profile=load_demo_profile(),
    )


@app.get("/api/v1/demo/clip")
def controlled_demo_clip() -> FileResponse:
    if not demo_cache.available():
        raise HTTPException(
            status_code=404,
            detail="The controlled demo cache is unavailable.",
        )

    return FileResponse(
        demo_cache.cache_path(demo_cache.CLIP_FILENAME),
        media_type="video/mp4",
        filename=demo_cache.CLIP_FILENAME,
        headers={"Cache-Control": "public, max-age=3600"},
    )


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

    if settings.controlled_demo_enabled and not demo_cache.available():
        problems.append("The controlled demo cache is incomplete")

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

            is_controlled_demo = await asyncio.to_thread(
                demo_cache.matches_clip,
                source_path,
            )

            if is_controlled_demo:
                await asyncio.to_thread(
                    demo_cache.copy_clip_to,
                    normalized_path,
                )
                controlled_fallback = await asyncio.to_thread(
                    demo_cache.analysis,
                )
            else:
                await asyncio.to_thread(
                    normalize_video,
                    source_path,
                    normalized_path,
                )
                controlled_fallback = None

            try:
                quality = await asyncio.to_thread(
                    assess_video_quality,
                    normalized_path,
                )
                quality_warnings = quality.warnings
            except VideoQualityError:
                logger.warning("Video quality inspection was unavailable")
                quality_warnings = []

            analysis_started_at = perf_counter()

            if controlled_fallback is None:
                analysis, source = await asyncio.to_thread(
                    analyze_video,
                    normalized_path,
                    duration_ms,
                )
            else:
                analysis, source = await asyncio.to_thread(
                    analyze_video,
                    normalized_path,
                    duration_ms,
                    controlled_fallback,
                )

            analysis.warnings = [
                *analysis.warnings,
                *quality_warnings,
            ][-10:]

            if not analysis.events:
                analysis.warnings = [
                    *analysis.warnings,
                    "No useful visible objects were detected. Try a brighter, steadier clip or use the rehearsal demo.",
                ][-10:]

            logger.info(
                "Gemini scene analysis completed in %.2f seconds",
                perf_counter() - analysis_started_at,
            )

            return AnalyzeVideoResponse(
                analysis=analysis,
                source=source,
            )

    except (
        MediaValidationError,
        DemoCacheError,
    ) as error:
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
                prepare_video_for_source,
                source_path,
                normalized_path,
                request.analysis_source,
                request.events,
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
        DemoCacheError,
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
                prepare_video_for_source,
                source_path,
                normalized_path,
                simulation_request.analysis_source,
                [simulation_request.event],
            )

            return await asyncio.to_thread(
                simulate_object_colors,
                normalized_path,
                simulation_request.event,
                duration_ms,
            )
    except (
        MediaValidationError,
        DemoCacheError,
        ColorSimulationError,
    ) as error:
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

        if story_request.analysis_source == "controlled_demo":
            await asyncio.to_thread(
                demo_cache.require_matching_clip,
                source_path,
            )
            await asyncio.to_thread(
                demo_cache.validate_events,
                story_request.events,
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

    except (MediaValidationError, DemoCacheError) as error:
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
        variation_id=story_request.variation_id,
        animation_seed=story_request.animation_seed,
        music_track_id=music_track_id(story_request.animation_seed),
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
        artifact_source=record.artifact_source,
        voice_source=record.voice_source,
        variation_id=record.variation_id,
        animation_seed=record.animation_seed,
        music_track_id=record.music_track_id,
        download_url=download_url,
    )


@app.delete(
    "/api/v1/story-jobs/{job_id}",
    status_code=204,
)
def cancel_story_job(job_id: str) -> None:
    if not re.fullmatch(r"[a-f0-9]{32}", job_id):
        raise HTTPException(status_code=404, detail="Story job not found.")

    record = job_store.get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Story job not found or expired.")
    if record.status in {"completed", "failed", "expired"}:
        return

    story_job_manager.cancel(job_id)


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
                record.story_source or "unknown"
            ),
            "X-PawSpective-Artifact-Source": (
                record.artifact_source or "unknown"
            ),
            "X-PawSpective-Voice-Source": (
                record.voice_source or "unknown"
            ),
        },
    )
