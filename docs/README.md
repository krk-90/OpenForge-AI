# OpenForge Documentation

OpenForge helps developers discover repositories, understand unfamiliar code, plan contributions, and review proposed changes. This documentation describes the current codebase and its operational requirements.

## Start here

- [Getting started](getting-started.md): local setup, required services, and deployment configuration.
- [API reference](API/api-reference.md): authentication, agent endpoints, request fields, and response shapes.
- [System overview](architecture/system-overview.md): application components and request flow.
- [Agent workflows](architecture/agent-workflows.md): what each agent does and which integrations it needs.
- [RAG indexing and retrieval](architecture/rag-indexing.md): how repository knowledge is prepared and queried.
- [Data and security](architecture/data-and-security.md): Supabase tables, ownership boundaries, and secret handling.
- [Testing and evaluation](operations/testing-and-evaluation.md): local test suite and live endpoint evaluation.
- [Architecture decision records](decisions/README.md): status and format for recording future decisions.

## Current scope

The React frontend currently provides email authentication, a repository-scoped contribution chat through the orchestrator, chat history, and session deletion. The API also exposes profile, mentor, pull-request review, repository RAG, documentation generation, and repository discovery endpoints. Their presence in the API does not imply that each has a dedicated frontend screen.

The app expects indexed repository content for repository RAG questions. The indexing implementation is a Python function; there is no public indexing endpoint in the current API.