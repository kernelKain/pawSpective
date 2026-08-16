import json
from pathlib import Path

from backend.app.contracts import (
    SceneAnalysisResponse,
    StoryReelRequest,
    StoryScriptResponse,
    VisibilityAnalysisResponse,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]

SCHEMAS = {
    "scene-analysis.schema.json": SceneAnalysisResponse,
    "visibility-analysis.schema.json": VisibilityAnalysisResponse,
    "story-reel-request.schema.json": StoryReelRequest,
    "story-script.schema.json": StoryScriptResponse,
}


def main() -> None:
    output_directory = PROJECT_ROOT / "contracts"
    output_directory.mkdir(parents=True, exist_ok=True)

    for filename, model in SCHEMAS.items():
        output_path = output_directory / filename
        output_path.write_text(
            json.dumps(model.model_json_schema(), indent=2),
            encoding="utf-8",
        )
        print(f"Schema written to {output_path}")


if __name__ == "__main__":
    main()