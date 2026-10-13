# OpenForge-AI
OpenForge is an AI-powered open source contribution mentor that helps developers discover, understand, and contribute to GitHub repositories. By combining GitHub intelligence, repository-aware RAG, and skill-based issue matching, OpenForge guides users from finding the right issue to submitting a successful pull request.

## Documentation

Start with the [documentation index](docs/README.md) for local setup, deployment, API usage, architecture, data and security, and evaluation.

## LangSmith tracing

OpenForge uses LangChain's automatic LangSmith tracing for LLM calls and explicit redacted spans around FastAPI agent routes and internal processing steps (orchestration, RAG retrieval/generation, mentor, PR review, documentation, and GitHub tool stages). When tracing is enabled, these nested spans help follow a request through the pipeline. Add these server-side variables to your local `.env` or Render environment to inspect runs, latency, errors, and intermediate steps in the `openforge-ai` project:

```env
LANGSMITH_TRACING=true
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_API_KEY=your_langsmith_api_key
LANGSMITH_PROJECT=openforge-ai
```

Tracing is opt-in and requires a valid API key. Keep the key server-side; never add it to frontend environment variables or commit real secrets. Prompts and model outputs may contain repository or user data, so configure LangSmith workspace access and data-retention settings appropriately.

## Run locally

Install the Python dependencies and configure the server environment variables in `.env` using `.env.example` as a template. Apply `SUPABASE/setup.sql` to your Supabase project before signing in.

Run the API from the repository root:

```powershell
python -m pip install -r requirements.txt
python -m uvicorn APP.main:app --reload
```

For frontend development with Vite's API proxy, run this in a second terminal:

```powershell
cd APP/Frontend
npm ci
npm run dev
```

Open `http://localhost:5173` for the frontend or `http://localhost:8000` for the API-served production build. To build the frontend bundle without Docker, run `npm run build` from `APP/Frontend`.

## Docker and Render

Create a local environment file from the template, then start the service with Docker Compose:

```powershell
Copy-Item .env.example .env
# Edit .env and add your real server-side credentials.
docker compose up --build -d
docker compose ps
docker compose logs -f openforge-ai
```

Stop and remove the Compose service and its default network with:

```powershell
docker compose down
```

To build the image without Compose, run `docker build -t openforge-ai .`. The image runs as a non-root user and includes a `/health` health check. The root `render.yaml` deploys the same multi-stage Docker image. In Render, provide `SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, and `GROQ_API_KEY`; `GITHUB_TOKEN` enables GitHub MCP tools. Keep service-role credentials and all API keys in Render's server-side environment, never in the React app.

    ## Supabase setup

    Configure `SUPABASE_URL`, `SUPABASE_KEY` (the anon key), and
    `SUPABASE_SERVICE_ROLE_KEY` in the project `.env`. Keep the service-role key
    server-side only. Run the complete `SUPABASE/setup.sql` file in the Supabase
    SQL Editor to create the application tables, vector/graph storage, and retrieval
    functions.

    The storage migration covers Supabase Auth-linked developer profiles, generated
    documentation, repository search history, agent conversation memory, and the
    user-scoped agent response cache. The RAG migration covers indexed chunks,
    repository knowledge, graph nodes and edges, and hybrid/vector search functions.

    After login, create a chat with `POST /agents/sessions` using the bearer access
    token. Reuse the returned `session_id` on agent requests. `GET /agents/sessions`
    lists only the current user's chats; `GET /agents/sessions/{session_id}` returns
    that chat's history, and `DELETE` removes that user's chat and its memory.

    ## Online evaluation

    Set `OPENFORGE_EVAL_ACCESS_TOKEN` to an access token for a dedicated evaluation
    user and `OPENFORGE_EVAL_REPOSITORY_ID` to an indexed `owner/name` repository,
    then run `python -m Evalution.online`. The runner exercises the agent endpoints
    over HTTP, checks response contracts and persisted chat history, and deletes its
    temporary chat unless `--keep-session` is supplied. Documentation and
    repository-discovery calls report as skipped when GitHub MCP is unavailable.