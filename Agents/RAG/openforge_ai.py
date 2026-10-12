from __future__ import annotations

import asyncio
import os
from typing import Any

from langchain_groq import ChatGroq

from Agents.RAG.generator.generation import generate_answer
from Agents.RAG.retriever.retrieval import RetrievedChunk
from Agents.RAG.retriever.retrieval import SupabaseRetriever
from Agents.RAG.router import route_query


async def ask_codebase_question(
    question: str,
    user_id: str,
    repository_id: str,
    limit: int = 6,
    *,
    llm=None,
    retriever: SupabaseRetriever | None = None,
) -> dict[str, Any]:
    """Retrieve repository-scoped evidence and generate a cited answer."""
    active_retriever = retriever or SupabaseRetriever(user_id, repository_id)
    plan = route_query(question)
    chunks = await asyncio.to_thread(
        active_retriever.search,
        question,
        limit,
        route=plan,
    )
    if plan.intent in {"overview", "architecture"}:
        knowledge_loader = getattr(active_retriever, "get_repository_knowledge", None)
        if knowledge_loader is not None:
            knowledge = await asyncio.to_thread(knowledge_loader)
            if knowledge:
                chunks.insert(0, RetrievedChunk(
                    text=(
                        f"Repository summary: {knowledge.get('summary', '')}\n"
                        f"Architecture: {knowledge.get('architecture', '')}"
                    ).strip(),
                    source="Repository knowledge",
                    chunk_kind="hierarchical",
                    metadata=knowledge.get("metadata", {}),
                ))
    sources = []
    seen: set[str] = set()
    for chunk in chunks:
        if chunk.source not in seen:
            seen.add(chunk.source)
            sources.append({
                "file": chunk.source,
                "language": chunk.language,
                "chunk_type": chunk.chunk_type,
                "similarity": chunk.similarity,
            })

    if not chunks:
        answer = "I don't have any indexed files for this repository yet."
    else:
        active_llm = llm or ChatGroq(
            model=os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"),
            temperature=0,
            max_tokens=1024,
        )
        answer = await generate_answer(active_llm, question, chunks, intent=plan.intent)
    return {
        "answer": answer,
        "sources": sources,
        "chunk_count": len(chunks),
        "route": plan.intent,
    }


__all__ = ["ask_codebase_question"]