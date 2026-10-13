# API Reference

The API is served by FastAPI. Interactive OpenAPI documentation is available at `/docs` when the server is running. Unless noted otherwise, agent and session endpoints require `Authorization: Bearer <Supabase access token>`.

## Service and authentication

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| `GET` | `/health` | No | Returns `{"status":"ok"}`. |
| `GET` | `/agents` | No | Lists available agent names and paths. |
| `POST` | `/auth/signup` | No | Creates an email/password account. Body: `{"email":"...","password":"..."}`. |
| `POST` | `/auth/login` | No | Signs in. Body: `{"email":"...","password":"..."}`. |

Auth responses include `message`, `user`, and `session`. Depending on Supabase email-confirmation settings, signup may return `session: null`; the client must then complete email confirmation and sign in. Login returns access and refresh tokens when successful.

## Chat sessions

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/agents/sessions` | Create a session. Body fields: `repository_id` (optional, defaults to empty string) and `title` (optional, defaults to `New chat`). Returns HTTP 201 and `{"session": ...}`. |
| `GET` | `/agents/sessions` | List the current user's sessions. Optional `limit` is 1-100, default 50. Returns `{"sessions":[...]}`. |
| `GET` | `/agents/sessions/{session_id}` | Read an owned session and its messages. Returns `{"session": ..., "messages":[...]}`. |
| `DELETE` | `/agents/sessions/{session_id}` | Delete an owned session and its conversation memory. Returns `{"deleted":true}`. |

Session ownership is checked against the authenticated Supabase user. Missing or unowned sessions return 404.

## Agent endpoints

All endpoints below require an existing session owned by the caller, except `GET /agents/profile` and `GET /agents/repository-discovery/history`.

### `POST /agents/orchestrator`

Body: `message` (1-10,000 characters), `session_id`, `repository_id`, and optional `repository_context` (defaults to empty string; max 30,000 characters). Returns `{"answer":"..."}`. The orchestrator uses the supplied repository context and persists the turn; it does not fetch repository context itself.

### `POST /agents/mentor`

Uses the same core fields as the orchestrator, with optional `profile` object and `issue` object or string. Returns guidance fields: `issue_summary`, `learning_objectives`, `concepts`, `approach_steps`, `first_task`, `suggested_commands`, `likely_pitfalls`, and `follow_up_questions`. Supply repository context to ground the guidance.

### `POST /agents/profile` and `GET /agents/profile`

POST body: `session_id` and `profile`. Profile fields include `display_name`, `github_username`, `bio`, `skills`, `interests`, `preferred_languages`, `experience_level` (`beginner`, `intermediate`, or `advanced`), and `contribution_goals`. Term fields accept strings or sequences and are normalized to unique trimmed strings. POST returns the normalized `profile` and `discovery_terms`; GET returns the persisted `profile` or 404 when none exists.

### `POST /agents/pr-review`

Body: `session_id`, `owner`, `repo`, `pull_number` (positive integer), optional `diff` (max 100,000 characters), and optional `additional_context` (max 20,000 characters). If `diff` is omitted, the service fetches the pull request through GitHub MCP. Returns `summary`, `findings`, `tests_to_run`, and `recommendation` (`needs_changes`, `approve_with_nits`, or `approve`). Findings use severity `critical`, `high`, `medium`, `low`, or `info`, with optional file, line, and suggestion. This endpoint returns advisory analysis and does not post a GitHub review.

### `POST /agents/rag/query`

Body: `session_id`, `repository_id`, `question` (1-10,000 characters), and `limit` (1-20, default 6). Returns `answer`, `sources`, `chunk_count`, and `route`. Sources identify files/chunks used. If no chunks are indexed for the user and repository, the answer says that indexed files are unavailable.

### `POST /agents/documentation`

Body: `session_id` and `request`. The nested request contains:

- `repository.repo_url` (GitHub repository URL), `branch` (default `main`), optional `commit_sha`, `analysis_depth` (`basic`, `intermediate`, `deep`), and `output_mode` (`markdown`, `json`, `html`).
- `explanation_type`: `repository`, `folder`, `file`, `class`, or `function`.
- `target_path` is required except for repository-wide documentation.
- `target_audience`: `beginner`, `intermediate`, or `expert`; default `intermediate`.
- `max_words`: 500-5,000; default 1,500.
- `include_diagrams`, `include_contributor_guide`, and `include_improvements` are booleans, all defaulting to true.

Returns `{"document":"..."}`. GitHub MCP is required; unavailable tools produce HTTP 503.

### `POST /agents/repository-discovery`

Body: `session_id` and `skills`, a list of 1-30 strings. Returns `{"repositories":[...]}`; each recommendation contains `repository`, `score`, `stars`, `language`, and `reason`. GitHub MCP and a Groq model are required.

### `GET /agents/repository-discovery/history`

Lists the authenticated user's saved repository searches. Optional `limit` is 1-100, default 20. Returns `{"searches":[...]}`.

## Common errors

| Status | Meaning |
| --- | --- |
| `401` | Missing or invalid bearer token, or invalid login credentials. |
| `404` | Requested session/profile was not found for the authenticated user. |
| `422` | Request validation failed or an agent could not process the supplied input. |
| `502` | An upstream model or agent operation failed. |
| `503` | Persistence, RAG, or a required optional integration is unavailable. |

Request validation errors use FastAPI's standard validation response. Error details may be intentionally generic; inspect server logs for the underlying exception.