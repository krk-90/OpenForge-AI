from __future__ import annotations

from Agents.RAG.retriever.retrieval import RetrievedChunk


class ContextCompressor:
    def compress(self, chunks: list[RetrievedChunk], max_chars: int = 8000) -> list[RetrievedChunk]:
        compressed: list[RetrievedChunk] = []
        seen_text: set[tuple[str, str]] = set()
        remaining = max_chars
        for chunk in chunks:
            normalized = " ".join(chunk.text.split())
            identity = (chunk.source, normalized)
            if not normalized or identity in seen_text or remaining <= 0:
                continue
            text = normalized[:remaining].rsplit(" ", 1)[0]
            if not text:
                continue
            seen_text.add(identity)
            compressed.append(RetrievedChunk(
                text=text,
                source=chunk.source,
                similarity=chunk.similarity,
                language=chunk.language,
                chunk_type=chunk.chunk_type,
                chunk_kind=chunk.chunk_kind,
                symbols=chunk.symbols,
                metadata=chunk.metadata,
                score=chunk.score,
                bm25_score=chunk.bm25_score,
                graph_score=chunk.graph_score,
            ))
            remaining -= len(text)
        return compressed


__all__ = ["ContextCompressor"]