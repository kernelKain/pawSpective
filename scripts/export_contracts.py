import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.contracts import (
    ColorSimulationResponse,
    SceneAnalysisResponse,
    StoryReelRequest,
    StoryScriptResponse,
    VisibilityAnalysisResponse,
)


CONTRACTS = {
    "scene-analysis.schema.json": SceneAnalysisResponse,
    "visibility-analysis.schema.json": VisibilityAnalysisResponse,
    "color-simulation.schema.json": ColorSimulationResponse,
    "story-reel-request.schema.json": StoryReelRequest,
    "story-script.schema.json": StoryScriptResponse,
}


def main() -> None:
    directory = PROJECT_ROOT / "contracts"
    directory.mkdir(parents=True, exist_ok=True)

    for filename, model in CONTRACTS.items():
        (directory / filename).write_text(
            json.dumps(model.model_json_schema(), indent=2) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
