# Data and Security

## Authentication and authorization

Email/password account creation and login are delegated to Supabase Auth. Protected API routes accept a Supabase access token as a bearer token; the backend validates it and derives the user ID rather than trusting a user ID supplied in the request.

For session-backed operations, the route checks that `(user_id, session_id)` exists before reading or changing session data. Session listing and deletion are scoped to the authenticated user. Profiles, search history, cache entries, and RAG data are also read or written with a user scope.

## Supabase clients and keys

- `SUPABASE_KEY` is the anon/public key used with Auth token validation.
- `SUPABASE_SERVICE_ROLE_KEY` is used by `DATABASE/supabase_db.py` for persistence.
- `SUPABASE_SERVICE_ROLE_KEY` bypasses normal row-level restrictions and must remain server-only. Never place it in frontend variables or commit it to source control.
- `SUPABASE/setup.sql` enables row-level security and creates owner policies for application and RAG tables.

The service-role client is privileged; route-level ownership checks are therefore an important application boundary in addition to database policies. Do not expose database credentials or raw service-role access to clients.

## Stored application data

| Table | Stored data |
| --- | --- |
| `developer_profiles` | User profile, skills, interests, languages, experience, and goals. |
| `generated_docs` | Generated repository documents by user and repository name. |
| `repository_search_history` | Search query, result count, results, and timestamp. |
| `agent_chat_sessions` | User-owned session ID, repository ID, title, and timestamps. |
| `agent_conversation_memory` | User/session-scoped serialized agent turns. |
| `agent_response_cache` | User-scoped cached agent responses with expiry. |
| `rag_documents` | Repository chunks, metadata, and vector embeddings. |
| `rag_repository_knowledge` | Repository-level summary and architecture. |
| `rag_graph_nodes`, `rag_graph_edges` | User/repository-scoped graph entities and relationships. |

Deleting a chat removes its conversation memory and session row. It does not delete the user's profile, repository-search history, generated documentation, response-cache rows, or repository RAG index.

## External data flows

- Model prompts and repository context are sent to the configured Groq model provider.
- GitHub MCP uses `GITHUB_TOKEN` to access GitHub when the relevant tools are enabled.
- Live evaluation calls the configured OpenForge HTTP service with a Supabase access token.
- Optional LangSmith tracing is enabled only when `LANGSMITH_TRACING` or `LANGCHAIN_TRACING_V2` is truthy. Review tracing configuration and provider policies before enabling it in a sensitive environment.

Keep credentials in environment variables or the deployment secret manager. Avoid logging bearer tokens, service-role keys, or unnecessary private repository content.