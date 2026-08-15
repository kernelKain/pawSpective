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
    media_directory: Path
    max_video_duration_seconds: int
    max_upload_bytes: int
    cors_origins: tuple[str, ...]


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
    cors_origins=env_origins(),
)