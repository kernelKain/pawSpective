from __future__ import annotations

from pathlib import Path

from scripts.check_markdown_links import DEFAULT_INPUTS, check_links


def test_repository_markdown_links_are_valid() -> None:
    checked, errors = check_links(DEFAULT_INPUTS)
    assert checked > 0
    assert errors == []


def test_missing_markdown_target_is_reported(tmp_path: Path) -> None:
    source = tmp_path / "README.md"
    source.write_text("[missing](docs/not-there.md)\n", encoding="utf-8")
    checked, errors = check_links([source], tmp_path)
    assert checked == 1
    assert len(errors) == 1
    assert "missing target" in errors[0]


def test_missing_markdown_anchor_is_reported(tmp_path: Path) -> None:
    source = tmp_path / "README.md"
    target = tmp_path / "target.md"
    source.write_text("[section](target.md#absent)\n", encoding="utf-8")
    target.write_text("# Present\n", encoding="utf-8")
    _, errors = check_links([source], tmp_path)
    assert len(errors) == 1
    assert "missing anchor" in errors[0]
