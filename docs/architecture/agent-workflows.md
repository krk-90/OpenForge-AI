# Agent Workflows

All session-backed routes require a valid Supabase bearer token and an existing session owned by the authenticated user. Shared memory records agent requests and responses, so agent activity can be read with the session-history endpoint.

## Orchestrator

`POST /agents/orchestrator` builds a conversation prompt from the user's message, repository identifier, caller-provided repository context, and recent persisted history. It calls Groq and persists the resulting turn. It does not use GitHub MCP to fetch repository data.

## Mentor

`POST /agents/mentor` validates an optional developer profile and asks the model for structured learning objectives, concepts, a stepwise approach, a first task, commands, pitfalls, and follow-up questions. Repository context is required by the agent implementation. The route includes recent session history with the issue input and caches results per user.

## Profile

`POST /agents/profile` normalizes profile terms, derives discovery terms from skills/interests/languages, persists the profile, and records the interaction. `GET /agents/profile` retrieves the authenticated user's profile.

## Pull-request reviewer

`POST /agents/pr-review` accepts an explicit diff or fetches PR information/files using GitHub MCP. It asks the model to report actionable defects only, with severity and changed-file locations when available. It returns structured findings and a recommendation; it does not modify GitHub state. An explicit diff avoids the need for GitHub MCP.

## Repository discovery

`POST /agents/repository-discovery` searches GitHub once per supplied skill, saves search results as per-user history, deduplicates candidates, applies a local heuristic score, keeps the leading candidates, and asks a Groq model to rerank them. Search and reranking require GitHub MCP and Groq respectively.

## Documentation generator

`POST /agents/documentation` reads a repository tree and a bounded selection of source files through GitHub MCP, then requests structured documentation from Groq. The implementation limits tree entries, source file count, per-file text, and total prompt context. It validates the generated JSON against `RepositoryDocumentation` before formatting/returning it. The endpoint returns generated text in a `document` field.

## Repository RAG question answering

`POST /agents/rag/query` routes the question, retrieves chunks scoped to the user and repository, optionally adds stored repository-level knowledge for overview/architecture questions, and generates an answer with source metadata. See [RAG indexing and retrieval](rag-indexing.md).

## MCP behavior

The MCP server initializes GitHub MCP through Docker when Docker is found, or through `npx` otherwise. It returns an empty tool list if no server can be configured or initialization fails. The HTTP routes translate missing required MCP features to HTTP 503. The pull-request reviewer is the exception when the request includes a diff.

The server allows a named set of read-only GitHub tools. Other `github*` tools are available only when `GITHUB_MCP_ALLOW_WRITE=true`; non-GitHub tools are not filtered by that check. Treat the token as privileged and do not enable write access unless the deployment requires it.