import json
from pathlib import Path

from backend.app.contracts import SceneAnalysisResponse


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_PATH = PROJECT_ROOT / "contracts" / "scene-analysis.schema.json"


def main() -> None:
    schema = SceneAnalysisResponse.model_json_schema()

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(schema, indent=2),
        encoding="utf-8",
    )

    print(f"Schema written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()