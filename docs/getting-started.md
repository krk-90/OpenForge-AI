# Getting Started

## Requirements

- Python 3.12 is the version used by the production Docker image.
- Node.js 22 is used to build the frontend image.
- A Supabase project with Auth enabled.
- A Groq API key for model-backed agents.
- A GitHub token and either Docker or `npx` for GitHub MCP workflows.

## Configure Supabase

1. Create a Supabase project and configure email/password authentication.
2. Copy `.env.example` to `.env` and set the Supabase project URL and anon key.
3. Add the Supabase service-role key. Keep it server-side and never expose it to the browser.
4. Run the complete `SUPABASE/setup.sql` script in the Supabase SQL Editor. It creates application tables, RAG tables, vector search support, and access policies.

The API validates bearer access tokens with Supabase Auth. Database persistence uses the service-role client, so both `SUPABASE_KEY` and `SUPABASE_SERVICE_ROLE_KEY` are required for the full application.

## Configure model and GitHub integrations

Set `GROQ_API_KEY` and, optionally, `GROQ_MODEL`. The default model used by most agents is `openai/gpt-oss-120b`; repository RAG defaults to `openai/gpt-oss-20b`.

Set `GITHUB_TOKEN` to enable GitHub MCP-backed discovery and documentation. The MCP server uses Docker when available and otherwise invokes the GitHub MCP package through `npx`. Without GitHub MCP, the pull-request reviewer can still work when a diff is supplied directly; repository discovery and documentation return HTTP 503.

GitHub MCP write-capable tools are filtered unless `GITHUB_MCP_ALLOW_WRITE=true`. Enabling write tools should be an explicit deployment decision.

## Run locally

From the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Set-Location APP/Frontend
npm install
npm run dev
```

For the production-like single-server experience, build the frontend and run FastAPI from the repository root:

```powershell
Set-Location APP/Frontend
npm run build
Set-Location ../..
uvicorn APP.main:app --reload --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`. The root page serves `APP/Frontend/dist/index.html`; it raises an error if the frontend has not been built. FastAPI's interactive API schema is available at `/docs`, and `/health` is the deployment health check.

The Vite development server serves the frontend separately. The frontend's API calls use relative paths, so use the built frontend behind FastAPI for a local end-to-end run unless a development proxy is configured.

## Deploy with Render

The repository includes a Docker-based Render service definition. It builds the frontend, installs Python requirements, and serves the app on Render's `PORT` (default 10000) with `/health` as its health check.

Configure these secrets in the Render service environment:

- `SUPABASE_URL`
- `SUPABASE_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- `GROQ_API_KEY`
- `GITHUB_TOKEN` when GitHub MCP features are needed

There is a configuration mismatch to account for: `render.yaml` currently declares `GITHUB_PERSONAL_ACCESS_TOKEN`, but the MCP server reads `GITHUB_TOKEN`. Set `GITHUB_TOKEN` in Render for MCP features to initialize. The Render file also does not currently declare `SUPABASE_SERVICE_ROLE_KEY`; add it as a secret environment variable in the service dashboard.

## First authenticated request

Create an account with `POST /auth/signup`, then sign in with `POST /auth/login`. Use the returned `session.access_token` as `Authorization: Bearer <token>`. Create a chat session with `POST /agents/sessions` and reuse its `session_id` for agent calls. See the [API reference](API/api-reference.md) for payloads and response details.