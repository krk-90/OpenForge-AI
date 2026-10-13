# RAG Indexing and Retrieval

## Indexing

Repository indexing is implemented by `Agents.RAG.indexer.index_repository_files`; it is not exposed as an HTTP endpoint. The caller supplies a local repository directory, a user ID, and a repository identifier such as `owner/name`. The routine:

1. Loads repository files and context, applying file-size limits and code intelligence.
2. Builds regular document chunks, symbol/AST chunks, and hierarchical repository/file/folder summaries.
3. Embeds the chunks with FastEmbed. The default model is `BAAI/bge-small-en-v1.5`, which produces 384-dimensional vectors; `RAG_EMBEDDING_MODEL` can select another compatible model.
4. Upserts chunk rows in batches into `rag_documents` with source path, language, chunk kind, symbols, metadata, commit, and embedding.
5. Stores repository summary/architecture and graph nodes/edges in their corresponding tables.

Default chunking uses 800 words with 120 words of overlap. The indexer accepts batch, file-size, chunk-size, and overlap overrides. The model dimension must stay compatible with the `vector(384)` column and SQL functions.

For example, from a Python process running at the project root:

```python
from Agents.RAG.indexer import index_repository_files

count = index_repository_files(
    user_id="<Supabase user UUID>",
    repository_id="owner/name",
    local_path="<path to cloned repository>",
)
print(f"Indexed {count} chunks")
```

`delete_repository_rag_documents(user_id, repository_id)` removes that user's chunks, graph nodes/edges, and repository knowledge for the scope.

## Retrieval and answer generation

The RAG API builds a query plan, searches repository-scoped stored content, and passes retrieved chunks to answer generation. For overview and architecture intents it also loads the repository summary and architecture record. The response includes a route label, chunk count, answer, and deduplicated source metadata.

`SUPABASE/rag.sql` defines vector similarity matching, PostgreSQL full-text document search, graph-node search, and graph expansion functions, plus indexes and owner policies. The retriever implementation decides which sources/functions to use for a query; the database functions are scoped by both `user_id` and `repository_id`.

If no chunks are available, the endpoint returns an explicit no-indexed-files answer instead of generating an unsupported repository answer. A repository ID alone does not cause indexing; index data must already exist.

## Schema essentials

- `rag_documents`: content chunks and 384-dimensional embeddings.
- `rag_repository_knowledge`: repository-level summary and architecture.
- `rag_graph_nodes`: searchable symbols/entities and summaries.
- `rag_graph_edges`: typed relationships between graph nodes.

The complete schema is installed by `SUPABASE/setup.sql`. See [Data and security](data-and-security.md) for ownership details.