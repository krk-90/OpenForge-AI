# OpenForge AI

<p align="center">
  <strong>Build confidence. Understand codebases. Contribute to open source.</strong>
  <br />
  An AI-powered contribution companion that helps developers explore repositories, discover relevant issues, and prepare stronger contributions.
  <br /><br />
  <a href="https://openforge-ai-wbjh.onrender.com/"><strong>Live Demo</strong></a>
  ·
  <a href="https://github.com/krk-90/OpenForge-AI">Source Code</a>
</p>

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/Python-FastAPI-3776AB?style=flat-square&logo=python&logoColor=white" />
  <img alt="React" src="https://img.shields.io/badge/Frontend-React%20%2B%20Vite-61DAFB?style=flat-square&logo=react&logoColor=black" />
  <img alt="LLM" src="https://img.shields.io/badge/LLM-Groq-F55036?style=flat-square" />
  <img alt="Database" src="https://img.shields.io/badge/Auth%20%26%20Data-Supabase-3FCF8E?style=flat-square&logo=supabase&logoColor=white" />
  <img alt="Deployment" src="https://img.shields.io/badge/Deployment-Render-46E3B7?style=flat-square&logo=render&logoColor=black" />
</p>

---

## Overview

Contributing to an unfamiliar open-source project can be difficult: the codebase may be large, issues can be hard to evaluate, and contribution guidelines take time to understand. **OpenForge AI** brings repository-aware AI assistance into one workflow, helping developers move from discovery to a more informed contribution.

The application combines a React frontend, FastAPI backend, LLM-powered agent workflows, GitHub MCP integration, retrieval-augmented generation (RAG), and Supabase-backed authentication and data.

> **Project status:** Live deployment, actively evolving. Features depend on configuration, available integrations, and indexed repository data. This README describes the intended workflow without implying that every backend capability has a dedicated UI.

## Live application

**Try OpenForge AI:** https://openforge-ai-wbjh.onrender.com/

The deployed application may take a short time to wake up when hosted on an on-demand instance. Use the live link to explore the current UI; avoid entering secrets or sensitive repository information into a demo.

## Problem and solution

| Challenge for contributors | How OpenForge helps |
|---|---|
| Finding projects that fit their skills | GitHub profile context and skill-oriented issue discovery |
| Understanding an unfamiliar repository | Repository-aware questions grounded in indexed content |
| Getting unstuck while learning a project | AI contribution mentoring and codebase guidance |
| Checking a proposed change before a PR | Pull request readiness review |
| Keeping track of agent conversations | User-associated chat history and session management |

OpenForge is an assistant, not an authority. Verify generated advice against source code, tests, repository documentation, and maintainer guidelines.

## Key features

- **GitHub profile analysis** — use developer context to guide contribution discovery.
- **Skill-based issue matching** — identify contribution opportunities worth investigating.
- **Repository Q&A with RAG** — ask questions using indexed repository knowledge.
- **AI contribution mentor** — get help navigating unfamiliar code and workflows.
- **Pull request readiness review** — receive feedback before opening a pull request.
- **Repository documentation support** — generate or explore repository-specific documentation.
- **Authenticated chat history** — list, retrieve, and delete the current user's sessions.
- **MCP-powered GitHub tools** — connect agent workflows to GitHub operations when configured.
- **Optional LangSmith tracing** — inspect supported LLM workflows when tracing is enabled.

Feature availability depends on service configuration. Repository Q&A requires indexed content, and some API capabilities may not yet have a dedicated frontend screen.

## Architecture

```text
┌───────────────────────────────────────────────┐
│             React + Vite Frontend             │
│       User interface · Authenticated flows    │
└───────────────────────┬───────────────────────┘
                        │ HTTP / API
┌───────────────────────▼───────────────────────┐
│               FastAPI Application             │
│       Routes · Validation · User context       │
└─────────────┬──────────────┬──────────────────┘
              │              │
     ┌────────▼────────┐  ┌──▼──────────────────┐
     │ Agent workflow  │  │ Supabase            │
     │ Groq LLM        │  │ Auth + application  │
     │ Orchestration   │  │ data / PostgreSQL   │
     └────────┬────────┘  └─────────────────────┘
              │
     ┌────────▼────────┐  ┌─────────────────────┐
     │ GitHub MCP      │  │ Repository RAG      │
     │ Repository tools│  │ Indexed content     │
     └─────────────────┘  └─────────────────────┘

       Optional observability: LangSmith
       Deployment: Docker + Render
```

### Request flow

1. A user interacts with the frontend and authenticates through the configured Supabase setup.
2. The frontend sends a request to the FastAPI backend.
3. The relevant route invokes the configured agent workflow, retrieval logic, or GitHub MCP tools.
4. The LLM and connected tools help produce a response; repository-grounded answers depend on available indexed data.
5. Supported conversations are associated with the authenticated user, and optional tracing can help inspect execution.

## Technology stack

| Layer | Technologies |
|---|---|
| Frontend | React, Vite |
| Backend | Python, FastAPI |
| LLM | Groq API |
| Agent and tool integration | Agent orchestration, Model Context Protocol (MCP) |
| GitHub integration | GitHub MCP tools |
| Retrieval | Repository-aware RAG and hybrid/vector retrieval functions |
| Authentication and data | Supabase Auth, PostgreSQL |
| Observability | Optional LangSmith tracing |
| Deployment | Docker, Render Blueprint |

## Getting started locally

### Prerequisites

- Python version supported by the project's dependencies
- Node.js and npm
- A Supabase project
- A Groq API key
- Docker, if using the containerized setup

### 1. Clone the repository

```bash
git clone https://github.com/krk-90/OpenForge-AI.git
cd OpenForge-AI
```

### 2. Install backend dependencies

From the repository root, run:

```powershell
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Configure the required values in `.env`. Apply `SUPABASE/setup.sql` to your Supabase project before testing authentication.

### 3. Start the API

```powershell
python -m uvicorn APP.main:app --reload
```

### 4. Start the frontend

In a second terminal:

```powershell
cd APP/Frontend
npm ci
npm run dev
```

Open **http://localhost:5173**. Vite proxies API requests during development. To serve the production frontend through FastAPI, build the frontend with `npm run build` in `APP/Frontend`; the generated assets are served from `APP/Frontend/dist` at **http://localhost:8000**.

## Environment variables

Set secrets locally in `.env` or through your deployment provider's secret settings. Never commit real credentials.

| Variable | Purpose |
|---|---|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_KEY` | Supabase anon/publishable key |
| `SUPABASE_SERVICE_ROLE_KEY` | Privileged server-side operations; never expose to the browser |
| `GROQ_API_KEY` | Access to the configured LLM |
| `GITHUB_TOKEN` | Optional authenticated GitHub MCP access; use least privilege |
| `GITHUB_MCP_ALLOW_WRITE` | Enables or disables write-capable GitHub MCP tools; keep disabled unless explicitly needed |
| `LANGSMITH_TRACING` | Set to `true` to enable tracing |
| `LANGSMITH_API_KEY` | Server-side LangSmith API key |
| `LANGSMITH_ENDPOINT` | LangSmith API endpoint, normally `https://api.smith.langchain.com` |
| `LANGSMITH_PROJECT` | LangSmith project name, for example `openforge-ai` |

Refer to `.env.example` and the deployment configuration for the complete set of variables used by the current codebase.

## Docker

The root Dockerfile builds the frontend and runs FastAPI in one container. It includes the GitHub MCP server binary, runs the application as a non-root user, and binds to Render's `PORT` (defaulting to `10000` locally).

```powershell
docker compose up --build -d
docker compose ps
docker compose logs -f openforge-ai
docker compose down
```

## Deployment on Render

The root `render.yaml` defines the Render Blueprint. Configure required environment variables and secrets in the Render service settings before deploying.

**Live deployment:** https://openforge-ai-wbjh.onrender.com/

Post-deployment smoke checks:

1. `GET /health` returns a healthy response.
2. `GET /` serves the frontend.
3. Sign-up and login work with the configured Supabase project.
4. Authenticated repository requests can reach GitHub MCP when it is configured.
5. Build and runtime logs show expected MCP initialization messages when GitHub MCP is enabled.

The default setup is intended to keep GitHub MCP read-only. If tools fail to load, inspect build and runtime logs and confirm that Render deployed the intended commit.

## Security and data handling

- Keep provider API keys and the Supabase service-role key on the server.
- Apply `SUPABASE/setup.sql` to create the required tables and retrieval functions.
- Use the authenticated user's access token for protected API requests.
- Scope conversation and session operations to the authenticated user.
- Keep GitHub MCP read-only unless write access is explicitly required and reviewed.
- Treat model output, retrieved repository content, and tool results as untrusted input.
- Review generated commands and code changes before executing or merging them.
- If tracing is enabled, limit access to traces and avoid sending secrets or unnecessary personal data.

See [Data and security](docs/architecture/data-and-security.md) for implementation details.

## Observability

LangSmith tracing is optional and disabled unless `LANGSMITH_TRACING=true` is configured. Set the LangSmith environment variables in the deployment settings to enable it. Never put the LangSmith API key in frontend variables or commit it to Git.

## Testing and evaluation

Run the online evaluation against a deployed API using a dedicated evaluation account and an indexed repository:

```bash
python -m Evalution.online --base-url "https://openforge-ai-wbjh.onrender.com" --output "evaluation-report.json"
```

Configure `OPENFORGE_EVAL_ACCESS_TOKEN` and `OPENFORGE_EVAL_REPOSITORY_ID` for that account and repository. The runner checks HTTP response contracts and persisted chat history, and removes its temporary chat unless `--keep-session` is supplied. Documentation and repository-discovery checks are reported as skipped when GitHub MCP is unavailable.

### Latest recorded online run

Date: **October 14, 2026** · Target: [Live deployment](https://openforge-ai-wbjh.onrender.com/)

| Measure | Result |
|---|---:|
| Checks passed | 8 / 9 |
| Pass rate | 88.89% |
| Failed checks | 1 |
| Total run duration | 61.33 s |
| Slowest successful agent request | Repository RAG, 19.20 s |

The **documentation** endpoint returned **HTTP 502** in this run (9.27 s). This is a recorded failure, not a passing result; inspect the Render runtime logs for the corresponding request before attributing the cause. Orchestrator, mentor, profile, PR review, repository RAG, repository discovery, session listing, and saved chat-history checks passed.

This is one online run and measures API behavior, not answer quality. It does **not** establish RAG Recall@K/MRR, groundedness, correctness, prompt-injection resistance, token usage, or load-test performance. Latencies are from this run only and are not service-level guarantees.

See [Testing and evaluation](docs/operations/testing-and-evaluation.md) for the current scope. Skipped checks are not passing evaluations; report measured results rather than claiming uncollected metrics.

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

Contributions and constructive feedback are welcome.

1. Read the project documentation and relevant contribution guidelines.
2. Reproduce the issue and understand the surrounding code before changing it.
3. Keep changes focused and add or update tests where appropriate.
4. Never commit credentials, user data, or generated secrets.
5. Open a pull request with a clear summary and test details.

## License

Check the repository's license file for the terms that apply to this project.
