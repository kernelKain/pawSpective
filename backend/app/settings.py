import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_origins() -> tuple[str, ...]:
    value = os.getenv(
        "PAWSPECTIVE_CORS_ORIGINS",
        "http://localhost:3000",
    )

    return tuple(
        origin.strip()
        for origin in value.split(",")
        if origin.strip()
    )


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str
    gemini_model: str
    demo_mode: bool
    allow_demo_fallback: bool
    controlled_demo_enabled: bool
    demo_cache_directory: Path
    media_directory: Path
    max_video_duration_seconds: int
    max_upload_bytes: int
    cors_origins: tuple[str, ...]

    elevenlabs_api_key: str
    elevenlabs_dog_voice_id: str
    elevenlabs_model_id: str

    jobs_directory: Path
    job_database: Path
    job_ttl_seconds: int
    max_concurrent_story_jobs: int
    story_jobs_per_hour: int


settings = Settings(
    gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
    gemini_model=os.getenv(
        "GEMINI_MODEL",
        "gemini-3.6-flash",
    ),
    demo_mode=env_bool("PAWSPECTIVE_DEMO_MODE", True),
    allow_demo_fallback=env_bool(
        "PAWSPECTIVE_ALLOW_DEMO_FALLBACK",
        True,
    ),
    controlled_demo_enabled=env_bool(
        "PAWSPECTIVE_CONTROLLED_DEMO_ENABLED",
        True,
    ),
    demo_cache_directory=Path(
        os.getenv(
            "PAWSPECTIVE_DEMO_CACHE_DIRECTORY",
            "demo_cache",
        ),
    ),
    media_directory=Path(
        os.getenv("PAWSPECTIVE_MEDIA_DIRECTORY", "media"),
    ),
    max_video_duration_seconds=int(
        os.getenv(
            "PAWSPECTIVE_MAX_VIDEO_DURATION_SECONDS",
            "15",
        ),
    ),
    max_upload_bytes=int(
        os.getenv(
            "PAWSPECTIVE_MAX_UPLOAD_BYTES",
            str(30 * 1024 * 1024),
        ),
    ),
    elevenlabs_api_key=os.getenv(
        "ELEVENLABS_API_KEY",
        "",
    ),
    elevenlabs_dog_voice_id=os.getenv(
        "ELEVENLABS_DOG_VOICE_ID",
        "",
    ),
    elevenlabs_model_id=os.getenv(
        "ELEVENLABS_MODEL_ID",
        "eleven_flash_v2_5",
    ),
        jobs_directory=Path(
        os.getenv(
            "PAWSPECTIVE_JOBS_DIRECTORY",
            "media/jobs",
        ),
    ),
    job_database=Path(
        os.getenv(
            "PAWSPECTIVE_JOB_DATABASE",
            "media/jobs.sqlite3",
        ),
    ),
    job_ttl_seconds=max(
        300,
        int(
            os.getenv(
                "PAWSPECTIVE_JOB_TTL_SECONDS",
                "3600",
            ),
        ),
    ),
    max_concurrent_story_jobs=max(
        1,
        int(
            os.getenv(
                "PAWSPECTIVE_MAX_CONCURRENT_STORY_JOBS",
                "1",
            ),
        ),
    ),
    story_jobs_per_hour=max(
        1,
        int(
            os.getenv(
                "PAWSPECTIVE_STORY_JOBS_PER_HOUR",
                "5",
            ),
        ),
    ),
    cors_origins=env_origins(),
)
