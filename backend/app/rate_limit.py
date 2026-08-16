import threading
import time
from collections import defaultdict, deque


class SlidingWindowRateLimiter:
    def __init__(
        self,
        limit: int,
        window_seconds: int,
    ) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self.entries: dict[str, deque[float]] = defaultdict(
            deque,
        )
        self.lock = threading.Lock()

    def retry_after(self, key: str) -> int:
        now = time.time()
        cutoff = now - self.window_seconds

        with self.lock:
            entries = self.entries[key]

            while entries and entries[0] <= cutoff:
                entries.popleft()

            if len(entries) >= self.limit:
                return max(
                    1,
                    round(
                        entries[0]
                        + self.window_seconds
                        - now
                    ),
                )

            entries.append(now)
            return 0