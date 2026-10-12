from __future__ import annotations

from pathlib import Path

from Agents.RAG.indexer import delete_repository_rag_documents, index_repository_files


def index_user_files(
    user_id: str,
    repository_id: str,
    paths: str | Path | list[str | Path],
    *,
    client=None,
    embedder=None,
) -> int:
    roots = [paths] if isinstance(paths, (str, Path)) else list(paths)
    total = 0
    for path in roots:
        resolved = Path(path).expanduser().resolve()
        if resolved.is_file():
            total += index_repository_files(
                user_id,
                repository_id,
                resolved.parent,
                [resolved.name],
                client=client,
                embedder=embedder,
            )
        else:
            total += index_repository_files(
                user_id,
                repository_id,
                resolved,
                client=client,
                embedder=embedder,
            )
    return total


def delete_user_source(
    user_id: str,
    repository_id: str,
    source: str,
    *,
    client=None,
) -> None:
    if client is None:
        from DATABASE.supabase_db import get_supabase_client

        client = get_supabase_client()
    for table_name in ("rag_documents", "rag_graph_edges", "rag_graph_nodes"):
        (
            client.table(table_name)
            .delete()
            .eq("user_id", user_id)
            .eq("repository_id", repository_id)
            .eq("source", source)
            .execute()
        )


__all__ = ["delete_repository_rag_documents", "delete_user_source", "index_user_files"]