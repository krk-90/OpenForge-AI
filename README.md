# OpenForge-AI

OpenForge is an AI-powered open-source contribution mentor that helps developers discover, understand, and contribute to GitHub repositories. It combines GitHub intelligence, repository-aware RAG, and skill-based issue matching to guide users from finding a suitable issue to preparing a contribution.

## Documentation

Start with the [documentation index](docs/README.md) for local setup, deployment, API usage, architecture, data and security, and evaluation.

## Run locally

1. Install Python dependencies and create a local environment file:

   ```powershell
   python -m pip install -r requirements.txt
   Copy-Item .env.example .env
   ```

2. Add your server-side credentials to `.env`. Apply `SUPABASE/setup.sql` to your Supabase project before signing in.

3. Start the API from the repository root:

   ```powershell
   python -m uvicorn APP.main:app --reload
   ```

4. For frontend development with Vite's API proxy, open a second terminal:

   ```powershell
   cd APP/Frontend
   npm ci
   npm run dev
   ```

Open `http://localhost:5173` for Vite's development frontend. The API serves the built frontend at `http://localhost:8000` after `npm run build` has created `APP/Frontend/dist`.

## Docker and Render

The root `Dockerfile` builds the React frontend and runs the FastAPI application in a single container. It also bundles GitHub's maintained native MCP server binary, avoiding the deprecated npm server and a Docker-in-Docker requirement on Render. The app runs as a non-root user, binds to Render's `PORT` (defaulting to `10000` locally), and exposes `/health` for health checks. The Docker build verifies that the Python MCP adapter imports successfully, so an incompatible SDK fails during build.

Run locally:

```powershell
docker compose up --build -d
docker compose ps
docker compose logs -f openforge-ai
docker compose down
```

Render uses the root `render.yaml` Blueprint. Configure these secrets in the Render service environment; never commit real credentials or expose them through frontend variables:

- `SUPABASE_URL`
- `SUPABASE_KEY` (Supabase anon/publishable key)
- `SUPABASE_SERVICE_ROLE_KEY` (server-side only)
- `GROQ_API_KEY`
- `GITHUB_TOKEN` (enables GitHub MCP tools; use a least-privilege token)

The Blueprint defaults `GITHUB_MCP_ALLOW_WRITE=false` so GitHub MCP starts in read-only mode. Keep it false unless you intentionally enable and review write-capable tools.

After deployment, verify:

1. `GET /health` returns `{"status":"ok"}`.
2. `GET /` serves the frontend.
3. Sign-up/login works with the configured Supabase project.
4. A repository lookup invokes GitHub MCP and returns results.
5. Render logs contain `MCP adapter imports OK` during the image build and `Loaded N MCP tools` at runtime when GitHub MCP is configured. In read-only mode, the server exposes only explicitly allowlisted read tools; write-capable and unknown tools are excluded by default.

If GitHub MCP tools fail to load, check the build/runtime logs and confirm the deployed image was rebuilt from this branch. The Docker build includes an import smoke test so incompatible MCP SDK versions fail during build rather than silently breaking the integration after deployment.

## LangSmith tracing

Tracing is opt-in. The Render Blueprint defaults `LANGSMITH_TRACING=false`. To enable it, add these server-side environment variables in Render:

```env
LANGSMITH_TRACING=true
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_API_KEY=your_langsmith_api_key
LANGSMITH_PROJECT=openforge-ai
```

Never put the LangSmith key in frontend variables or commit it. Traces can contain metadata about user requests and repository activity; configure workspace access and retention appropriately.

## Supabase setup

Configure `SUPABASE_URL`, `SUPABASE_KEY`, and `SUPABASE_SERVICE_ROLE_KEY` in the project environment. Keep the service-role key server-side only. Run the complete `SUPABASE/setup.sql` file in the Supabase SQL Editor to create the application tables and retrieval functions.

The SQL setup covers Supabase Auth-linked developer profiles, generated documentation, repository search history, agent conversation memory, response cache, indexed chunks, repository knowledge, graph data, and hybrid/vector search functions.

After login, create a chat with `POST /agents/sessions` using the bearer access token. Reuse the returned `session_id` on agent requests. `GET /agents/sessions` lists only the current user's chats; `GET /agents/sessions/{session_id}` returns that chat's history, and `DELETE` removes that user's chat and its memory.

## Online evaluation

Set `OPENFORGE_EVAL_ACCESS_TOKEN` to an access token for a dedicated evaluation user and `OPENFORGE_EVAL_REPOSITORY_ID` to an indexed `owner/name` repository, then run:

```bash
python -m Evalution.online
```

The runner exercises the agent endpoints over HTTP, checks response contracts and persisted chat history, and deletes its temporary chat unless `--keep-session` is supplied. Documentation and repository-discovery checks are reported as skipped when GitHub MCP is unavailable.
