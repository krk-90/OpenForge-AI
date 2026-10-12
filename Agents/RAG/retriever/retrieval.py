from __future__ import annotations

import logging
import math
import os
import re
from dataclasses import dataclass
from typing import Any

from Agents.RAG.indexer import DEFAULT_EMBEDDING_MODEL
from Agents.RAG.router import QueryPlan, route_query


logger = logging.getLogger(__name__)
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+")


@dataclass(frozen=True)
class RetrievedChunk:
    text: str
    source: str
    similarity: float = 0.0
    language: str = ""
    chunk_type: str = ""
    chunk_kind: str = "semantic"
    symbols: tuple[str, ...] = ()
    metadata: dict | None = None
    score: float = 0.0
    bm25_score: float = 0.0
    graph_score: float = 0.0


class SupabaseRetriever:
    def __init__(
        self,
        user_id: str,
        repository_id: str,
        *,
        client: Any | None = None,
        embedder: Any | None = None,
    ):
        if not user_id.strip() or not repository_id.strip():
            raise ValueError("user_id and repository_id are required for scoped RAG retrieval")
        self.user_id = user_id
        self.repository_id = repository_id
        self.client = client
        self.embedder = embedder

    def _dependencies(self):
        if self.client is None:
            from DATABASE.supabase_db import get_supabase_client

            self.client = get_supabase_client()
        if self.embedder is None:
            try:
                from fastembed import TextEmbedding
            except ImportError as exc:
                raise RuntimeError("Install fastembed to use repository RAG retrieval") from exc
            self.embedder = TextEmbedding(
                model_name=os.getenv("RAG_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)
            )

    def search(
        self,
        question: str,
        limit: int = 6,
        *,
        route: QueryPlan | None = None,
    ) -> list[RetrievedChunk]:
        if not question.strip():
            raise ValueError("question must not be empty")
        if limit <= 0:
            raise ValueError("limit must be positive")
        self._dependencies()
        vectors = list(self.embedder.embed([question]))
        if not vectors:
            return []
        plan = route or route_query(question)
        params = {
            "query_embedding": [float(value) for value in vectors[0]],
            "match_user_id": self.user_id,
            "match_repository_id": self.repository_id,
            "match_count": max(limit * 4, 12),
        }
        dense_rows = self._rpc_rows("match_rag_documents", params, required=True)
        lexical_rows = self._rpc_rows(
            "search_rag_documents",
            {
                "query_text": question,
                "match_user_id": self.user_id,
                "match_repository_id": self.repository_id,
                "match_count": max(limit * 4, 12),
            },
        )
        graph_rows = self._graph_rows(question, max(limit * 2, 8))
        return _fuse_and_rerank(
            dense_rows,
            lexical_rows,
            graph_rows,
            question,
            plan,
            limit,
        )

    def get_repository_knowledge(self) -> dict | None:
        self._dependencies()
        try:
            response = (
                self.client.table("rag_repository_knowledge")
                .select("summary,architecture,metadata")
                .eq("user_id", self.user_id)
                .eq("repository_id", self.repository_id)
                .maybe_single()
                .execute()
            )
        except Exception:
            logger.debug("Repository knowledge lookup is unavailable", exc_info=True)
            return None
        return response.data if isinstance(response.data, dict) else None

    def _rpc_rows(self, name: str, arguments: dict, *, required: bool = False) -> list[dict]:
        try:
            response = self.client.rpc(name, arguments).execute()
        except Exception:
            if required:
                raise
            logger.debug("Optional RAG retrieval path %s is unavailable", name, exc_info=True)
            return []
        return [row for row in (response.data or []) if isinstance(row, dict)]

    def _graph_rows(self, question: str, limit: int) -> list[dict]:
        arguments = {
            "query_text": question,
            "match_user_id": self.user_id,
            "match_repository_id": self.repository_id,
            "match_count": limit,
        }
        nodes = self._rpc_rows("search_rag_graph_nodes", arguments)
        node_ids = [node.get("id") for node in nodes if node.get("id")]
        expanded = []
        if node_ids:
            expanded = self._rpc_rows(
                "expand_rag_graph_nodes",
                {
                    "match_node_ids": node_ids,
                    "match_user_id": self.user_id,
                    "match_repository_id": self.repository_id,
                    "match_count": limit,
                },
            )
        return nodes + expanded


def _fuse_and_rerank(
    dense_rows: list[dict],
    lexical_rows: list[dict],
    graph_rows: list[dict],
    question: str,
    plan: QueryPlan,
    limit: int,
) -> list[RetrievedChunk]:
    candidates: dict[str, dict] = {}
    sources = (
        (dense_rows, plan.dense_weight, False),
        (lexical_rows, plan.lexical_weight, False),
        (graph_rows, plan.graph_weight, True),
    )
    for rows, weight, is_graph in sources:
        for rank, row in enumerate(rows, 1):
            content = row.get("content", "")
            if is_graph:
                name = row.get("name", "")
                summary = row.get("summary", "")
                if not name and not summary:
                    continue
                relation = row.get("relation")
                content = f"{row.get('kind', 'graph')} {name}: {summary}".strip()
                if relation:
                    content += f" Related by {relation}."
            source = row.get("source") or row.get("file_path") or "unknown"
            if not content:
                continue
            identity = str(row.get("id") or f"{source}\0{content}")
            candidate = candidates.setdefault(identity, {
                "row": row,
                "content": content,
                "source": source,
                "fused": 0.0,
                "graph_score": 0.0,
                "similarity": 0.0,
                "is_graph": is_graph,
            })
            candidate["fused"] += weight / (60 + rank)
            candidate["similarity"] = max(
                candidate["similarity"],
                float(row.get("similarity") or 0.0),
            )
            if is_graph:
                candidate["graph_score"] = max(
                    candidate["graph_score"],
                    float(row.get("similarity") or 0.5),
                )
                candidate["is_graph"] = True

    if not candidates:
        return []
    bm25_scores = _bm25_scores(question, [item["content"] for item in candidates.values()])
    max_bm25 = max(bm25_scores, default=0.0) or 1.0
    max_fused = max(item["fused"] for item in candidates.values()) or 1.0
    ranked: list[RetrievedChunk] = []
    for candidate, bm25_score in zip(candidates.values(), bm25_scores):
        row = candidate["row"]
        normalized_bm25 = bm25_score / max_bm25
        normalized_fused = candidate["fused"] / max_fused
        # RRF stabilizes rankings across providers; BM25 and graph scores refine ties.
        score = 0.68 * normalized_fused + 0.22 * normalized_bm25
        score += 0.07 * min(max(candidate["similarity"], 0.0), 1.0)
        score += 0.03 * min(max(candidate["graph_score"], 0.0), 1.0)
        metadata = row.get("metadata")
        ranked.append(RetrievedChunk(
            text=candidate["content"],
            source=candidate["source"],
            similarity=candidate["similarity"],
            language=row.get("language", ""),
            chunk_type=row.get("chunk_type", ""),
            chunk_kind=row.get("chunk_kind", "graph" if candidate["is_graph"] else "semantic"),
            symbols=tuple(row.get("symbols") or ()),
            metadata=metadata if isinstance(metadata, dict) else {},
            score=score,
            bm25_score=normalized_bm25,
            graph_score=candidate["graph_score"],
        ))
    return sorted(ranked, key=lambda item: item.score, reverse=True)[:limit]


def _bm25_scores(query: str, documents: list[str]) -> list[float]:
    query_terms = _TOKEN_PATTERN.findall(query.casefold())
    tokenized = [_TOKEN_PATTERN.findall(document.casefold()) for document in documents]
    if not query_terms or not tokenized:
        return [0.0] * len(documents)
    document_frequency: dict[str, int] = {}
    for terms in tokenized:
        for term in set(terms):
            document_frequency[term] = document_frequency.get(term, 0) + 1
    average_length = sum(map(len, tokenized)) / max(len(tokenized), 1)
    scores = []
    for terms in tokenized:
        frequencies: dict[str, int] = {}
        for term in terms:
            frequencies[term] = frequencies.get(term, 0) + 1
        score = 0.0
        for term in query_terms:
            frequency = frequencies.get(term, 0)
            if not frequency:
                continue
            doc_frequency = document_frequency.get(term, 0)
            inverse = math.log(1 + (len(tokenized) - doc_frequency + 0.5) / (doc_frequency + 0.5))
            denominator = frequency + 1.2 * (
                1 - 0.75 + 0.75 * len(terms) / max(average_length, 1.0)
            )
            score += inverse * frequency * 2.2 / denominator
        scores.append(score)
    return scores


__all__ = ["RetrievedChunk", "SupabaseRetriever"]