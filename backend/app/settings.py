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
        origin.strip().rstrip("/")
        for origin in value.split(",")
        if origin.strip().rstrip("/")
    )


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str
    gemini_model: str
    gemini_analysis_fallback_model: str
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
    animation_enabled: bool
    omni_video_model: str
    veo_video_model: str
    animation_timeout_seconds: int
    allow_local_animation_fallback: bool


settings = Settings(
    gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
    gemini_model=os.getenv(
        "GEMINI_MODEL",
        "gemini-3.6-flash",
    ),
    gemini_analysis_fallback_model=os.getenv(
        "GEMINI_ANALYSIS_FALLBACK_MODEL",
        "gemini-3.1-flash-lite",
    ).strip(),
    demo_mode=env_bool("PAWSPECTIVE_DEMO_MODE", True),
    allow_demo_fallback=env_bool(
        "PAWSPECTIVE_ALLOW_DEMO_FALLBACK",
        True,
    ),
    controlled_demo_enabled=env_bool(
        "PAWSPECTIVE_CONTROLLED_DEMO_ENABLED",
        False,
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
    animation_enabled=env_bool(
        "PAWSPECTIVE_ANIMATION_ENABLED",
        True,
    ),
    omni_video_model=os.getenv(
        "PAWSPECTIVE_OMNI_VIDEO_MODEL",
        "gemini-omni-flash-preview",
    ),
    veo_video_model=os.getenv(
        "PAWSPECTIVE_VEO_VIDEO_MODEL",
        "veo-3.1-fast-generate-preview",
    ),
    animation_timeout_seconds=max(
        60,
        int(os.getenv("PAWSPECTIVE_ANIMATION_TIMEOUT_SECONDS", "420")),
    ),
    allow_local_animation_fallback=env_bool(
        "PAWSPECTIVE_ALLOW_LOCAL_ANIMATION_FALLBACK",
        True,
    ),
    cors_origins=env_origins(),
)
