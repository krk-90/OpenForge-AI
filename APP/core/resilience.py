from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from APP.core.tracing import invoke_traced

logger = logging.getLogger("openforge.metrics")
T = TypeVar("T")
RETRYABLE_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}


def _status_code(exc: Exception) -> int | None:
    for candidate in (getattr(exc, "status_code", None), getattr(getattr(exc, "response", None), "status_code", None)):
        try:
            if candidate is not None:
                return int(candidate)
        except (TypeError, ValueError):
            pass
    return None


def _is_retryable(exc: Exception) -> bool:
    status = _status_code(exc)
    if status is not None:
        return status in RETRYABLE_STATUS_CODES
    message = str(exc).casefold()
    return any(marker in message for marker in (
        "timeout", "temporarily unavailable", "connection reset",
        "connection error", "rate limit", "429", "502", "503", "504",
    ))


async def retry_async(
    operation: Callable[[], Awaitable[T]], *, attempts: int | None = None,
    base_delay: float | None = None,
) -> T:
    """Retry transient provider errors with bounded exponential backoff."""
    attempts = int(os.getenv("LLM_RETRY_ATTEMPTS", "3")) if attempts is None else attempts
    base_delay = float(os.getenv("LLM_RETRY_BASE_DELAY", "0.5")) if base_delay is None else base_delay
    attempts = max(1, min(int(attempts), 5))
    base_delay = max(0.0, min(float(base_delay), 4.0))
    for attempt in range(attempts):
        try:
            return await operation()
        except Exception as exc:
            if not _is_retryable(exc) or attempt == attempts - 1:
                raise
            delay = min(base_delay * (2 ** attempt) + random.uniform(0, 0.1), 8.0)
            logger.warning("llm_retry attempt=%s max_attempts=%s status_code=%s delay_seconds=%.3f",
                           attempt + 1, attempts, _status_code(exc), delay)
            await asyncio.sleep(delay)
    raise RuntimeError("Retry loop exited unexpectedly")


async def invoke_with_retry(llm: Any, input_data: Any, *, operation: str) -> Any:
    """Invoke a LangChain-compatible model with retries and safe latency/token telemetry."""
    started = time.perf_counter()
    try:
        result = await retry_async(lambda: invoke_traced(llm, input_data, operation))
        duration_ms = (time.perf_counter() - started) * 1000
        usage: Any = getattr(result, "usage_metadata", None)
        if not isinstance(usage, dict):
            response_metadata = getattr(result, "response_metadata", None)
            usage = response_metadata.get("token_usage", {}) if isinstance(response_metadata, dict) else {}
        if not isinstance(usage, dict):
            usage = {}
        input_tokens = usage.get("input_tokens", usage.get("prompt_tokens"))
        output_tokens = usage.get("output_tokens", usage.get("completion_tokens"))
        logger.info(json.dumps({
            "event": "llm_call", "operation": operation, "status": "success",
            "duration_ms": round(duration_ms, 2),
            "input_tokens": input_tokens, "output_tokens": output_tokens,
            "total_tokens": usage.get("total_tokens"),
        }, separators=(",", ":")))
        return result
    except Exception as exc:
        logger.error(json.dumps({
            "event": "llm_call", "operation": operation, "status": "error",
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "error_type": type(exc).__name__, "status_code": _status_code(exc),
        }, separators=(",", ":")))
        raise



async def invoke_with_fallback(llm: Any, input_data: Any, *, operation: str) -> Any:
    """Retry the primary model, then try configured compatible generation models."""
    try:
        return await invoke_with_retry(llm, input_data, operation=operation)
    except Exception as primary_error:
        configured = os.getenv(
            "LLM_FALLBACK_MODELS",
            "openai/gpt-oss-20b,openai/gpt-oss-120b",
        )
        current = str(getattr(llm, "model_name", getattr(llm, "model", "")))
        candidates = [name.strip() for name in configured.split(",") if name.strip()]
        candidates = [name for name in candidates if name != current]
        if not candidates:
            raise
        try:
            from LLM_gateway.provider.groq_llm import get_model
        except Exception:
            logger.exception("llm_fallback_unavailable operation=%s", operation)
            raise primary_error
        for model_name in candidates[:3]:
            try:
                fallback_llm = get_model(model_name)
                logger.warning("llm_fallback operation=%s model=%s", operation, model_name)
                return await invoke_with_retry(fallback_llm, input_data, operation=f"{operation}:fallback")
            except Exception:
                logger.exception("llm_fallback_failed operation=%s model=%s", operation, model_name)
        raise primary_error


class InMemoryRateLimitMiddleware(BaseHTTPMiddleware):
    """Per-client sliding-window limiter. Shared storage is required across instances."""
    def __init__(self, app, requests_per_minute: int = 60, window_seconds: int = 60):
        super().__init__(app)
        self.limit = max(1, requests_per_minute)
        self.window = max(1, window_seconds)
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in {"/health", "/docs", "/openapi.json"} or request.method == "OPTIONS":
            return await call_next(request)
        client = request.client.host if request.client else "unknown"
        now = time.monotonic()
        # Avoid unbounded memory growth from clients that send many unique source IPs.
        if client not in self.hits and len(self.hits) >= 10000:
            stale_before = now - self.window
            self.hits = defaultdict(deque, {
                key: bucket for key, bucket in self.hits.items()
                if bucket and bucket[-1] >= stale_before
            })
        bucket = self.hits[client]
        while bucket and now - bucket[0] >= self.window:
            bucket.popleft()
        if len(bucket) >= self.limit:
            retry_after = max(1, int(self.window - (now - bucket[0])))
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Please retry shortly."},
                headers={"Retry-After": str(retry_after)},
            )
        bucket.append(now)
        started = time.perf_counter()
        try:
            response = await call_next(request)
            response.headers["X-Process-Time-ms"] = f"{(time.perf_counter() - started) * 1000:.2f}"
            logger.info(json.dumps({
                "event": "http_request", "method": request.method,
                "path": request.url.path, "status_code": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            }, separators=(",", ":")))
            return response
        except Exception:
            logger.exception("http_request_failed method=%s path=%s", request.method, request.url.path)
            raise


def rate_limit_from_env() -> int:
    try:
        return max(1, int(os.getenv("API_RATE_LIMIT_PER_MINUTE", "60")))
    except ValueError:
        logger.warning("Invalid API_RATE_LIMIT_PER_MINUTE; defaulting to 60")
        return 60
