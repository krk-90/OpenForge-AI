from __future__ import annotations

from collections import defaultdict

from Agents.RAG.knowledge import RepositoryContext
from Agents.RAG.loading import DocumentChunk, chunk_documents


class ChunkingEngine:
    def __init__(self, chunk_size: int = 800, overlap: int = 120):
        if chunk_size <= 0 or overlap < 0 or overlap >= chunk_size:
            raise ValueError("chunk_size must be positive and overlap must be smaller than chunk_size")
        self.chunk_size = chunk_size
        self.overlap = overlap

    def build(self, context: RepositoryContext) -> list[DocumentChunk]:
        chunks = chunk_documents(
            context.documents,
            chunk_size=self.chunk_size,
            overlap=self.overlap,
        )
        chunks.extend(self._ast_chunks(context))
        chunks.extend(self._hierarchical_chunks(context))
        return chunks

    def _ast_chunks(self, context: RepositoryContext) -> list[DocumentChunk]:
        chunks = []
        counters: dict[str, int] = defaultdict(int)
        for analysis in context.analyses:
            for symbol in analysis.symbols:
                text = f"{symbol.signature}\n{symbol.text}".strip()
                parts = _split_words(text, self.chunk_size, self.overlap)
                for part_index, part in enumerate(parts):
                    chunk_id = counters[analysis.source]
                    counters[analysis.source] += 1
                    chunks.append(DocumentChunk(
                        part,
                        analysis.source,
                        chunk_id,
                        chunk_kind="ast",
                        symbols=(symbol.qualified_name,),
                        metadata={
                            "symbol_kind": symbol.kind,
                            "start_line": symbol.start_line,
                            "end_line": symbol.end_line,
                            "part": part_index,
                        },
                    ))
        return chunks

    def _hierarchical_chunks(self, context: RepositoryContext) -> list[DocumentChunk]:
        chunks = []
        counters: dict[str, int] = defaultdict(int)
        files = context.knowledge.files
        if context.documents:
            primary_source = next(
                (document.source for document in context.documents if document.source.lower().endswith("readme.md")),
                context.documents[0].source,
            )
            overview = (
                f"Repository overview: {context.knowledge.repo_summary}\n"
                f"Architecture: {context.knowledge.architecture}\n"
                f"Languages: {', '.join(context.knowledge.tech_stack)}"
            )
            _append_split_chunks(
                chunks,
                counters,
                primary_source,
                overview,
                self.chunk_size,
                self.overlap,
                metadata={
                    "level": "repository",
                    "source_files": [document.source for document in context.documents],
                },
            )

        for document in context.documents:
            file_info = files.get(document.source, {})
            symbol_names = file_info.get("symbols", [])
            summary = file_info.get("summary") or document.text[:240]
            content = (
                f"File: {document.source}\n"
                f"Language: {file_info.get('language', 'unknown')}\n"
                f"Symbols: {', '.join(symbol_names) or 'none detected'}\n"
                f"Summary: {summary}"
            )
            _append_split_chunks(
                chunks,
                counters,
                document.source,
                content,
                self.chunk_size,
                self.overlap,
                metadata={"level": "file", "source_files": [document.source]},
            )

        for folder, details in context.knowledge.folders.items():
            paths = details.get("files", [])
            if not paths:
                continue
            source = paths[0]
            content = (
                f"Directory: {folder}\n"
                f"Purpose: {details.get('purpose', 'Repository directory')}\n"
                f"Files: {', '.join(paths)}"
            )
            _append_split_chunks(
                chunks,
                counters,
                source,
                content,
                self.chunk_size,
                self.overlap,
                metadata={"level": "directory", "source_files": paths},
            )
        return chunks


def _append_split_chunks(
    chunks: list[DocumentChunk],
    counters: dict[str, int],
    source: str,
    text: str,
    chunk_size: int,
    overlap: int,
    *,
    metadata: dict,
) -> None:
    for part in _split_words(text, chunk_size, overlap):
        chunk_id = counters[source]
        counters[source] += 1
        chunks.append(DocumentChunk(
            part,
            source,
            chunk_id,
            chunk_kind="hierarchical",
            metadata=metadata,
        ))


def _split_words(text: str, chunk_size: int, overlap: int) -> list[str]:
    words = text.split()
    step = chunk_size - overlap
    parts = []
    for start in range(0, len(words), step):
        part = " ".join(words[start : start + chunk_size]).strip()
        if part:
            parts.append(part)
        if start + chunk_size >= len(words):
            break
    return parts


__all__ = ["ChunkingEngine"]