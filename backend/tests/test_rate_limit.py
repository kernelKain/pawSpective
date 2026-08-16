import backend.app.rate_limit as rate_limit_module
from backend.app.rate_limit import SlidingWindowRateLimiter


def test_sliding_window_limit_and_retry_after(
    monkeypatch,
) -> None:
    now = 100.0
    monkeypatch.setattr(
        rate_limit_module.time,
        "time",
        lambda: now,
    )

    limiter = SlidingWindowRateLimiter(
        limit=2,
        window_seconds=10,
    )

    assert limiter.retry_after("client-a") == 0
    assert limiter.retry_after("client-a") == 0

    now = 101.0
    assert limiter.retry_after("client-a") == 9

    assert limiter.retry_after("client-b") == 0

    now = 110.0
    assert limiter.retry_after("client-a") == 0
