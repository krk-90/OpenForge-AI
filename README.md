# OpenForge AI

**An AI-powered open-source contribution companion.** OpenForge helps developers discover relevant repositories, understand unfamiliar codebases, find issues that match their skills, and prepare more thoughtful contributions.

It brings together GitHub integration, repository-aware retrieval-augmented generation (RAG), agent workflows, and a web application backed by FastAPI and Supabase.

> **Project status:** Active development. Available endpoints and integrations can vary by configuration; see the documentation before assuming every capability has a dedicated UI.

## What OpenForge is designed to help with

- **GitHub profile analysis** — use developer context to guide contribution discovery.
- **Skill-based issue matching** — narrow down contribution opportunities to investigate.
- **Repository understanding** — ask questions grounded in indexed repository content.
- **AI contribution mentor** — get guidance while exploring an unfamiliar project.
- **Pull request readiness review** — review a proposed change before opening a PR.
- **Repository documentation** — generate and work with repository-specific knowledge.
- **Conversation history** — keep agent sessions associated with the authenticated user.

These capabilities depend on the configured services, indexed repository data, and available GitHub tools. OpenForge is a guide, not a substitute for reading the code, verifying suggestions, or following a project's contribution rules.

## How it works

```text
React + Vite frontend
        |
        v
FastAPI application and authenticated API routes
        |
        +--> Agent orchestrator and LLM (Groq)
        |
        +--> GitHub MCP tools for repository operations
        |
        +--> Repository retrieval (hybrid/vector search over indexed knowledge)
        |
        +--> Supabase Auth and PostgreSQL-backed application data
        |
        +--> Optional LangSmith tracing
```

Repository RAG questions require indexed content. The current indexing implementation is a Python function; there is no public indexing endpoint in the current API. The API exposes more capabilities than the frontend currently presents as dedicated screens.

## Tech stack

- **Frontend:** React, Vite
- **API:** Python, FastAPI
- **LLM:** Groq API
- **GitHub integration:** GitHub MCP server and MCP adapter
- **Auth and data:** Supabase Auth and PostgreSQL
- **Retrieval:** repository-aware RAG and hybrid/vector search functions
- **Observability:** optional LangSmith tracing
- **Deployment:** Docker and Render Blueprint

## Run locally

### Requirements

- Python version compatible with `requirements.txt`
- Node.js and npm
- A Supabase project
- A Groq API key
- Docker, if running the containerized version

### 1. Install dependencies

From the repository root, run:

```powershell
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Add the required server-side values to `.env`. Apply `SUPABASE/setup.sql` to your Supabase project before testing authentication.

### 2. Start the API

```powershell
python -m uvicorn APP.main:app --reload
```

### 3. Start the frontend in development mode

Open a second terminal:

```powershell
cd APP/Frontend
npm ci
npm run dev
```

Open **http://localhost:5173**. Vite proxies API requests during development. To have FastAPI serve the built frontend, run `npm run build` in `APP/Frontend`; the built assets are served from `APP/Frontend/dist` at **http://localhost:8000**.

## Environment configuration

Set secrets in your local `.env` or your deployment provider's secret/environment settings. Do not commit real credentials.

| Variable | Purpose |
|---|---|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_KEY` | Supabase anon/publishable key |
| `SUPABASE_SERVICE_ROLE_KEY` | Server-side privileged database operations; never expose to the browser |
| `GROQ_API_KEY` | LLM access |
| `GITHUB_TOKEN` | Optional authenticated GitHub MCP access; use least privilege |
| `GITHUB_MCP_ALLOW_WRITE` | Controls whether write-capable GitHub MCP tools may be enabled; keep `false` unless intentionally required |
| `LANGSMITH_TRACING` | Set to `true` to enable tracing |
| `LANGSMITH_API_KEY` | Server-side LangSmith API key |
| `LANGSMITH_ENDPOINT` | LangSmith endpoint, normally `https://api.smith.langchain.com` |
| `LANGSMITH_PROJECT` | Trace project name, for example `openforge-ai` |

Check `.env.example` and the deployment configuration for the complete set of variables used by the current codebase.

## Docker

The root Dockerfile builds the frontend and runs FastAPI in one container. It includes GitHub's maintained native MCP server binary, runs the application as a non-root user, and binds to Render's `PORT` (default `10000` locally). The image build also checks that the Python MCP adapter imports successfully.

```powershell
docker compose up --build -d
docker compose ps
docker compose logs -f openforge-ai
docker compose down
```

## Deploy to Render

The root `render.yaml` defines the Render Blueprint. Configure the environment variables and secrets listed above in the Render service settings, then deploy from the repository.

After deployment, check:

1. `GET /health` returns a healthy response.
2. `GET /` serves the frontend.
3. Sign-up and login work with the configured Supabase project.
4. An authenticated repository lookup can reach GitHub MCP when it is configured.
5. Logs show `MCP adapter imports OK` during build and `Loaded N MCP tools` at runtime when GitHub MCP is enabled.

The default configuration keeps GitHub MCP in read-only mode. Unknown or non-allowlisted tools should not be exposed in that mode. If tools fail to load, inspect the build and runtime logs and confirm that Render deployed the intended commit.

## Authentication and data safety

- Apply `SUPABASE/setup.sql` to create the required tables and retrieval functions.
- Keep the Supabase service-role key and all provider API keys on the server.
- Use the authenticated user's bearer access token for protected API requests.
- Agent sessions are scoped to the authenticated user. The API supports listing a user's sessions, retrieving an individual session, and deleting that user's session and associated memory.
- Keep GitHub MCP read-only unless write access is explicitly needed and reviewed.
- Treat model output, retrieved repository content, and tool results as untrusted input. Review proposed commands and code changes before running or merging them.
- Traces may include request metadata and repository activity. Limit access and retention, and avoid sending secrets or unnecessary personal data to tracing services.

See [Data and security](docs/architecture/data-and-security.md) for the current implementation details.

## LangSmith tracing

Tracing is optional and disabled unless `LANGSMITH_TRACING=true` is configured. Add the LangSmith environment variables in the Render service settings to enable it. Never place the LangSmith API key in frontend variables or commit it to the repository.

## Testing and evaluation

Run the online evaluation against a deployed API using a dedicated evaluation account and an indexed repository:

```bash
python -m Evalution.online
```

Configure `OPENFORGE_EVAL_ACCESS_TOKEN` and `OPENFORGE_EVAL_REPOSITORY_ID` for that account and repository. The runner checks HTTP response contracts and persisted chat history, and removes its temporary chat unless `--keep-session` is supplied. Documentation and repository-discovery checks are reported as skipped when GitHub MCP is unavailable.

For the broader testing strategy and current evaluation scope, see [Testing and evaluation](docs/operations/testing-and-evaluation.md). Do not interpret skipped checks as passing evaluations; report measured results rather than claiming metrics that have not been collected.

## Documentation

- [Documentation index](docs/README.md)
- [Getting started](docs/getting-started.md)
- [System overview](docs/architecture/system-overview.md)
- [Agent workflows](docs/architecture/agent-workflows.md)
- [RAG indexing and retrieval](docs/architecture/rag-indexing.md)
- [API reference](docs/API/api-reference.md)
- [Data and security](docs/architecture/data-and-security.md)
- [Testing and evaluation](docs/operations/testing-and-evaluation.md)

## Contributing

1. Read the repository documentation and the target project's contribution guidelines.
2. Reproduce the issue and understand the relevant code before changing it.
3. Keep changes focused and add or update tests when appropriate.
4. Never commit credentials, user data, or generated secrets.
5. Open a pull request with a clear explanation of the change and how it was tested.

## License

Check the repository's license file for the terms that apply to this project.
