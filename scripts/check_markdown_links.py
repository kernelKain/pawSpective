"""Check repository-local links and heading anchors in Markdown files."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from urllib.parse import unquote

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUTS = [
    PROJECT_ROOT / "README.md",
    PROJECT_ROOT / "docs",
]
LINK_PATTERN = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")


def markdown_anchors(path: Path) -> set[str]:
    anchors: set[str] = set()
    counts: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", line)
        if not match:
            continue
        heading = re.sub(r"[`*_~]", "", match.group(1)).strip().lower()
        slug = re.sub(r"[^\w\- ]", "", heading, flags=re.UNICODE)
        slug = re.sub(r"[\s\-]+", "-", slug).strip("-")
        duplicate = counts.get(slug, 0)
        counts[slug] = duplicate + 1
        anchors.add(slug if duplicate == 0 else f"{slug}-{duplicate}")
    return anchors


def collect_markdown(inputs: list[Path]) -> list[Path]:
    files: set[Path] = set()
    for item in inputs:
        if item.is_dir():
            files.update(item.rglob("*.md"))
        elif item.is_file() and item.suffix.lower() == ".md":
            files.add(item)
        else:
            raise ValueError(f"input does not exist or is not Markdown: {item}")
    return sorted(files)


def check_links(inputs: list[Path], project_root: Path = PROJECT_ROOT) -> tuple[int, list[str]]:
    files = collect_markdown(inputs)
    errors: list[str] = []
    checked = 0
    root = project_root.resolve()

    for source in files:
        text = source.read_text(encoding="utf-8")
        for match in LINK_PATTERN.finditer(text):
            destination = match.group(1).strip().split(maxsplit=1)[0].strip("<>")
            if not destination or destination.startswith(("http://", "https://", "mailto:", "data:")):
                continue
            checked += 1
            raw_path, separator, raw_anchor = destination.partition("#")
            target = (source.parent / unquote(raw_path)).resolve() if raw_path else source.resolve()
            line = text.count("\n", 0, match.start()) + 1
            label = f"{source.relative_to(root)}:{line}"
            try:
                target.relative_to(root)
            except ValueError:
                errors.append(f"{label}: link escapes repository: {destination}")
                continue
            if not target.exists():
                errors.append(f"{label}: missing target: {destination}")
                continue
            if separator:
                anchor = unquote(raw_anchor).lower()
                if not target.is_file() or target.suffix.lower() != ".md" or anchor not in markdown_anchors(target):
                    errors.append(f"{label}: missing anchor: {destination}")
    return checked, errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="*", type=Path)
    args = parser.parse_args()
    inputs = [path.resolve() for path in args.inputs] if args.inputs else DEFAULT_INPUTS
    try:
        checked, errors = check_links(inputs)
    except ValueError as error:
        parser.exit(1, f"Markdown link check failed: {error}\n")
    if errors:
        parser.exit(1, "Markdown link check failed:\n" + "\n".join(f"- {error}" for error in errors) + "\n")
    print(f"Markdown links valid: {checked} repository-local links checked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
