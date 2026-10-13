from __future__ import annotations

import asyncio
import os
import random
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from typing import TypeVar

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware

T = TypeVar("T")


async def retry_async(
    operation: Callable[[], Awaitable[T]], *, attempts: int | None = None,
    base_delay: float | None = None,
) -> T:
    """Retry transient provider failures with bounded exponential backoff."""
    attempts = attempts or int(os.getenv("LLM_RETRY_ATTEMPTS", "3"))
    base_delay = base_delay if base_delay is not None else float(os.getenv("LLM_RETRY_BASE_DELAY", "0.5"))
    attempts = max(1, min(attempts, 5))
    for attempt in range(attempts):
        try:
            return await operation()
        except Exception as exc:
            status_code = getattr(exc, "status_code", None)
            retryable = status_code in {408, 409, 425, 429, 500, 502, 503, 504} or any(
                marker in str(exc).lower()
                for marker in ("timeout", "temporarily unavailable", "connection reset", "rate limit", "429")
            )
            if not retryable or attempt == attempts - 1:
                raise
            await asyncio.sleep(min(base_delay * (2 ** attempt) + random.uniform(0, 0.2), 8.0))
    raise RuntimeError("Retry loop exited unexpectedly")


class InMemoryRateLimitMiddleware(BaseHTTPMiddleware):
    """Per-client sliding-window limiter; use shared Redis storage for multi-instance deployments."""
    def __init__(self, app, requests_per_minute: int = 60, window_seconds: int = 60):
        super().__init__(app)
        self.limit = max(1, requests_per_minute)
        self.window = max(1, window_seconds)
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        if request.url.path in {"/health", "/docs", "/openapi.json"} or request.method == "OPTIONS":
            return await call_next(request)
        client = request.client.host if request.client else "unknown"
        now = time.monotonic()
        bucket = self.hits[client]
        while bucket and now - bucket[0] >= self.window:
            bucket.popleft()
        if len(bucket) >= self.limit:
            retry_after = max(1, int(self.window - (now - bucket[0])))
            return __import__("starlette.responses", fromlist=["JSONResponse"]).JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Please retry shortly."},
                headers={"Retry-After": str(retry_after)},
            )
        bucket.append(now)
        return await call_next(request)


def rate_limit_from_env() -> int:
    try:
        return max(1, int(os.getenv("API_RATE_LIMIT_PER_MINUTE", "60")))
    except ValueError:
        return 60
