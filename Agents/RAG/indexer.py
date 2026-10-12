from __future__ import annotations

from hashlib import sha256
import logging
import os
from pathlib import Path
from typing import Any

from Agents.RAG.chunking import ChunkingEngine
from Agents.RAG.knowledge import RepositoryCache, load_repository_context


logger = logging.getLogger(__name__)
DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
LANGUAGE_BY_EXTENSION = {
    ".c": "c", ".cpp": "cpp", ".cs": "csharp", ".go": "go",
    ".java": "java", ".js": "javascript", ".jsx": "javascript",
    ".kt": "kotlin", ".md": "markdown", ".php": "php", ".py": "python",
    ".rb": "ruby", ".rs": "rust", ".sh": "shell", ".sql": "sql",
    ".swift": "swift", ".ts": "typescript", ".tsx": "typescript",
    ".yaml": "yaml", ".yml": "yaml", ".json": "json",
}
DOCUMENTATION_EXTENSIONS = {".md", ".rst", ".txt"}
CONFIGURATION_EXTENSIONS = {".json", ".sql", ".toml", ".xml", ".yaml", ".yml"}


def _create_embedder():
    try:
        from fastembed import TextEmbedding
    except ImportError as exc:
        raise RuntimeError("Install fastembed to use repository RAG indexing") from exc
    return TextEmbedding(model_name=os.getenv("RAG_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL))


def _row_id(
    user_id: str,
    repository_id: str,
    source: str,
    chunk_kind: str,
    chunk_id: int,
) -> str:
    value = f"{user_id}:{repository_id}:{source}:{chunk_kind}:{chunk_id}"
    return sha256(value.encode("utf-8")).hexdigest()


def index_repository_files(
    user_id: str,
    repository_id: str,
    local_path: str | Path,
    file_tree: list[str] | None = None,
    commit_sha: str = "",
    chunk_size: int = 800,
    overlap: int = 120,
    max_file_size_bytes: int = 512 * 1024,
    batch_size: int = 50,
    *,
    client: Any | None = None,
    embedder: Any | None = None,
    documentation: Any | None = None,
    repository_cache: RepositoryCache | None = None,
) -> int:
    """Analyze, chunk, embed, and persist a repository's knowledge and graph."""
    if not user_id.strip() or not repository_id.strip():
        raise ValueError("user_id and repository_id are required for scoped RAG indexing")
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")

    root = Path(local_path).expanduser().resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"Repository path is not a directory: {root}")
    context = load_repository_context(
        repository_id,
        root,
        file_tree=file_tree,
        max_file_size_bytes=max_file_size_bytes,
        documentation=documentation,
        cache=repository_cache,
        graph_namespace=f"{user_id}:{repository_id}",
    )
    chunks = ChunkingEngine(chunk_size, overlap).build(context)
    if not chunks:
        return 0

    if client is None:
        from DATABASE.supabase_db import get_supabase_client

        client = get_supabase_client()
    embedder = embedder or _create_embedder()

    total_indexed = 0
    for offset in range(0, len(chunks), batch_size):
        chunk_batch = chunks[offset : offset + batch_size]
        vectors = list(embedder.embed([chunk.text for chunk in chunk_batch]))
        if len(vectors) != len(chunk_batch):
            raise RuntimeError("Embedding model returned an unexpected number of vectors")
        rows = []
        for chunk, vector in zip(chunk_batch, vectors):
            extension = Path(chunk.source).suffix.lower()
            chunk_type = (
                "doc" if extension in DOCUMENTATION_EXTENSIONS
                else "config" if extension in CONFIGURATION_EXTENSIONS
                else "code"
            )
            rows.append({
                "id": _row_id(
                    user_id,
                    repository_id,
                    chunk.source,
                    chunk.chunk_kind,
                    chunk.chunk_id,
                ),
                "user_id": user_id,
                "repository_id": repository_id,
                "source": chunk.source,
                "file_path": chunk.source,
                "content": chunk.text,
                "chunk_id": chunk.chunk_id,
                "language": LANGUAGE_BY_EXTENSION.get(extension, "unknown"),
                "chunk_type": chunk_type,
                "chunk_kind": chunk.chunk_kind,
                "symbols": list(chunk.symbols),
                "metadata": chunk.metadata,
                "commit_sha": commit_sha,
                "embedding": [float(value) for value in vector],
            })
        client.table("rag_documents").upsert(rows, on_conflict="id").execute()
        total_indexed += len(rows)

    knowledge_payload = context.knowledge.model_dump(mode="json")
    knowledge_payload["code_intelligence"] = context.intelligence.to_dict()
    client.table("rag_repository_knowledge").upsert(
        {
            "user_id": user_id,
            "repository_id": repository_id,
            "repository_name": context.knowledge.repository_name,
            "summary": context.knowledge.repo_summary,
            "architecture": context.knowledge.architecture,
            "metadata": knowledge_payload,
        },
        on_conflict="user_id,repository_id",
    ).execute()

    graph_nodes = [
        {"user_id": user_id, "repository_id": repository_id, **row}
        for row in context.graph.to_node_rows()
    ]
    graph_edges = [
        {"user_id": user_id, "repository_id": repository_id, **row}
        for row in context.graph.to_edge_rows()
    ]
    if graph_nodes:
        client.table("rag_graph_nodes").upsert(graph_nodes, on_conflict="id").execute()
    if graph_edges:
        client.table("rag_graph_edges").upsert(graph_edges, on_conflict="id").execute()

    logger.info(
        "Indexed %d chunks for user=%s repository=%s",
        total_indexed,
        user_id,
        repository_id,
    )
    return total_indexed


def delete_repository_rag_documents(
    user_id: str,
    repository_id: str,
    *,
    client: Any | None = None,
) -> None:
    if client is None:
        from DATABASE.supabase_db import get_supabase_client

        client = get_supabase_client()
    for table_name in (
        "rag_documents",
        "rag_graph_edges",
        "rag_graph_nodes",
        "rag_repository_knowledge",
    ):
        (
            client.table(table_name)
            .delete()
            .eq("user_id", user_id)
            .eq("repository_id", repository_id)
            .execute()
        )


__all__ = ["delete_repository_rag_documents", "index_repository_files"]