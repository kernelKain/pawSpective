from backend.app.settings import env_origins


def test_env_origins_normalizes_whitespace_and_trailing_slashes(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "PAWSPECTIVE_CORS_ORIGINS",
        " https://paw.example.com/, https://preview.example.com ",
    )

    assert env_origins() == (
        "https://paw.example.com",
        "https://preview.example.com",
    )
