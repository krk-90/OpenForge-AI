from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv

load_dotenv()


def tracing_enabled() -> bool:
    value = os.getenv("LANGSMITH_TRACING", os.getenv("LANGCHAIN_TRACING_V2", "false"))
    return value.strip().lower() in {"1", "true", "yes", "on"}


def configure_langsmith_tracing() -> bool:
    """Enable LangChain tracing only when explicitly requested and keyed."""
    if not tracing_enabled():
        return False
    if not (os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY")):
        return False
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ.setdefault("LANGSMITH_PROJECT", "openforge-ai")
    return True


def trace_config(
    run_name: str,
    *,
    user_id: str | None = None,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build consistent LangChain run metadata without including secrets or prompts."""
    run_tags = ["openforge-ai", *(tags or [])]
    run_metadata: dict[str, Any] = {
        "service": "openforge-ai",
        "tracing_enabled": tracing_enabled(),
    }
    if user_id:
        run_metadata["user_id"] = user_id
    if metadata:
        run_metadata.update(metadata)

    return {
        "run_name": run_name,
        "tags": run_tags,
        "metadata": run_metadata,
    }


async def invoke_traced(
    llm: Any,
    input_data: Any,
    run_name: str,
    *,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> Any:
    if not tracing_enabled():
        return await llm.ainvoke(input_data)
    return await llm.ainvoke(
        input_data,
        config=trace_config(run_name, tags=tags, metadata=metadata),
    )


__all__ = ["configure_langsmith_tracing", "invoke_traced", "trace_config", "tracing_enabled"]
