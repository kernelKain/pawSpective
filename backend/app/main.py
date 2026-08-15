import asyncio
import tempfile
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.app.analysis import (
    SceneAnalysisError,
    analyze_video,
)
from backend.app.contracts import SceneAnalysisResponse
from backend.app.media import (
    ALLOWED_VIDEO_TYPES,
    MediaValidationError,
    normalize_video,
    probe_duration_ms,
    save_upload,
)
from backend.app.settings import settings


class AnalyzeVideoResponse(BaseModel):
    analysis: SceneAnalysisResponse
    source: Literal["gemini", "demo"]


app = FastAPI(
    title="PawSpective API",
    version="0.3.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
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

            analysis, source = await asyncio.to_thread(
                analyze_video,
                normalized_path,
                duration_ms,
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
