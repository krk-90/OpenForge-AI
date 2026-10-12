from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QueryPlan:
    intent: str
    dense_weight: float
    lexical_weight: float
    graph_weight: float


def route_query(question: str) -> QueryPlan:
    query = question.casefold()
    if any(term in query for term in (
        "overview", "summarize", "summary", "purpose", "what is this repository",
        "what does this repository do",
    )):
        intent = "overview"
        weights = (0.35, 0.25, 0.40)
    elif any(term in query for term in ("architecture", "dependency", "depends", "call graph", "data flow")):
        intent = "architecture"
        weights = (0.30, 0.20, 0.50)
    elif any(term in query for term in ("function", "class", "method", "where is", "where does", "how does")):
        intent = "code"
        weights = (0.45, 0.35, 0.20)
    else:
        intent = "search"
        weights = (0.40, 0.40, 0.20)
    return QueryPlan(intent, *weights)


__all__ = ["QueryPlan", "route_query"]