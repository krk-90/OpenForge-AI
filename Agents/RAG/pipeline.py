from __future__ import annotations

import asyncio

from Agents.RAG.generator.generation import generate_answer
from Agents.RAG.retriever.retrieval import RetrievedChunk, SupabaseRetriever
from Agents.RAG.router import route_query


class RAGPipeline:
    def __init__(
        self,
        llm,
        user_id: str,
        repository_id: str,
        *,
        retriever: SupabaseRetriever | None = None,
    ):
        self.llm = llm
        self.user_id = user_id
        self.repository_id = repository_id
        self.retriever = retriever or SupabaseRetriever(user_id, repository_id)

    def retrieve(self, question: str, limit: int = 6) -> list[RetrievedChunk]:
        return self.retriever.search(question, limit=limit)

    async def ask(self, question: str, limit: int = 6) -> str:
        plan = route_query(question)
        chunks = await asyncio.to_thread(
            self.retriever.search,
            question,
            limit,
            route=plan,
        )
        if plan.intent in {"overview", "architecture"}:
            knowledge = await asyncio.to_thread(self.retriever.get_repository_knowledge)
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
        if not chunks:
            return "I don't have enough indexed repository content to answer that question."
        return await generate_answer(self.llm, question, chunks, intent=plan.intent)


__all__ = ["RAGPipeline"]