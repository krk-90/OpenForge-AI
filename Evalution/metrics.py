"""Offline metrics for labelled retrieval and request-latency evaluation.

These functions calculate metrics from recorded, labelled runs. They do not call an
LLM or manufacture quality labels; populate a ground-truth dataset before reporting
quality scores.
"""
from __future__ import annotations

from statistics import mean
from typing import Any, Iterable


def recall_at_k(retrieved_ids: Iterable[str], relevant_ids: Iterable[str], k: int = 5) -> float:
    relevant = set(relevant_ids)
    if not relevant:
        raise ValueError("relevant_ids must contain at least one relevant document")
    if k < 1:
        raise ValueError("k must be >= 1")
    return len(set(list(retrieved_ids)[:k]) & relevant) / len(relevant)


def reciprocal_rank(retrieved_ids: Iterable[str], relevant_ids: Iterable[str]) -> float:
    relevant = set(relevant_ids)
    if not relevant:
        raise ValueError("relevant_ids must contain at least one relevant document")
    for rank, doc_id in enumerate(retrieved_ids, start=1):
        if doc_id in relevant:
            return 1.0 / rank
    return 0.0


def evaluate_retrieval(cases: list[dict[str, Any]], k: int = 5) -> dict[str, Any]:
    """Evaluate rows containing retrieved_ids and relevant_ids; report per-case and macro means."""
    if not cases:
        raise ValueError("At least one labelled evaluation case is required")
    rows = []
    for case in cases:
        retrieved = case.get("retrieved_ids", [])
        relevant = case.get("relevant_ids", [])
        rows.append({
            "id": case.get("id", f"case-{len(rows) + 1}"),
            "recall_at_k": recall_at_k(retrieved, relevant, k),
            "reciprocal_rank": reciprocal_rank(retrieved, relevant),
        })
    return {
        "case_count": len(rows),
        "k": k,
        "recall_at_k": round(mean(row["recall_at_k"] for row in rows), 4),
        "mrr": round(mean(row["reciprocal_rank"] for row in rows), 4),
        "cases": rows,
    }


def percentile(values: Iterable[float], percentile_value: float) -> float:
    """Nearest-rank percentile for non-empty latency samples."""
    data = sorted(float(value) for value in values)
    if not data:
        raise ValueError("At least one measurement is required")
    if not 0 < percentile_value <= 100:
        raise ValueError("percentile_value must be in (0, 100]")
    index = max(0, min(len(data) - 1, int((percentile_value / 100) * len(data) + 0.999999) - 1))
    return data[index]
