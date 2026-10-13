from __future__ import annotations

import logging
import os
import shutil

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

logger = logging.getLogger(__name__)

# Explicit allowlist: unknown tools are not assumed to be read-only.
_READ_ONLY_TOOLS = {
    "get_me",
    "get_repository",
    "search_repositories",
    "search_code",
    "get_file_contents",
    "get_tree",
    "list_branches",
    "list_commits",
    "get_commit",
    "list_tags",
    "list_releases",
    "get_latest_release",
    "list_issues",
    "search_issues",
    "get_issue",
    "list_pull_requests",
    "search_pull_requests",
    "get_pull_request",
    "get_pull_request_files",
    "get_pull_request_reviews",
    "get_pull_request_comments",
    "list_workflows",
    "list_workflow_runs",
    "get_workflow_run",
    "get_job_logs",
}


async def get_openforge_tools(
    repo_path: str | None = None,
) -> list[BaseTool]:
    server_configs = {}

    if repo_path and os.path.exists(repo_path):
        git_exe = shutil.which("mcp-server-git")

        if git_exe:
            logger.info("Git MCP enabled")

            server_configs["git"] = {
                "command": git_exe,
                "args": ["-r", repo_path],
                "transport": "stdio",
            }
        else:
            logger.warning("mcp-server-git not found")

    github_token = os.getenv("GITHUB_TOKEN")

    if github_token:
        # Prefer GitHub's maintained native server. Docker and the legacy
        # npm server are fallbacks for local development environments.
        github_exe = shutil.which("github-mcp-server")
        docker_exe = shutil.which("docker")

        if github_exe:
            logger.info("GitHub MCP using native server binary")
            server_configs["github"] = {
                "command": github_exe,
                "args": ["stdio"],
                "env": {
                    "GITHUB_PERSONAL_ACCESS_TOKEN": github_token,
                    "GITHUB_READ_ONLY": "1"
                    if os.getenv("GITHUB_MCP_ALLOW_WRITE", "false").lower() != "true"
                    else "0",
                },
                "transport": "stdio",
            }
        elif docker_exe:
            logger.info("GitHub MCP via Docker")
            server_configs["github"] = {
                "command": docker_exe,
                "args": [
                    "run",
                    "-i",
                    "--rm",
                    "-e",
                    "GITHUB_PERSONAL_ACCESS_TOKEN",
                    "-e",
                    "GITHUB_READ_ONLY",
                    "ghcr.io/github/github-mcp-server:v1.9.0",
                ],
                "env": {
                    "GITHUB_PERSONAL_ACCESS_TOKEN": github_token,
                    "GITHUB_READ_ONLY": "1"
                    if os.getenv("GITHUB_MCP_ALLOW_WRITE", "false").lower() != "true"
                    else "0",
                },
                "transport": "stdio",
            }
        elif shutil.which("npx"):
            logger.warning(
                "Native GitHub MCP binary unavailable; using deprecated npm fallback. "
                "Install github-mcp-server for production deployments."
            )
            server_configs["github"] = {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-github"],
                "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": github_token},
                "transport": "stdio",
            }
        else:
            logger.error(
                "GitHub MCP cannot start: github-mcp-server, Docker, and npx are unavailable"
            )
    else:
        logger.warning("GITHUB_TOKEN missing; GitHub MCP tools are disabled")

    if not server_configs:
        logger.warning("No MCP servers available")
        return []

    try:
        client = MultiServerMCPClient(server_configs)
        tools = await client.get_tools()

        allow_write = (
            os.getenv("GITHUB_MCP_ALLOW_WRITE", "false").strip().lower()
            == "true"
        )
        filtered_tools = []

        for tool in tools:
            # The official GitHub MCP server uses unprefixed tool names. Do
            # not infer that an unknown/unprefixed tool is safe to expose.
            if tool.name in _READ_ONLY_TOOLS or allow_write:
                filtered_tools.append(tool)
            else:
                logger.info(
                    "Skipping non-allowlisted MCP tool in read-only mode: %s",
                    tool.name,
                )

        unique_tools = {tool.name: tool for tool in filtered_tools}
        result = list(unique_tools.values())

        logger.info("Loaded %d MCP tools", len(result))
        for tool in result:
            logger.info("MCP tool enabled: %s", tool.name)

        if github_token and not result:
            logger.warning(
                "GitHub MCP connected but no allowlisted tools were loaded; "
                "check the server version and tool names."
            )

        return result

    except Exception:
        logger.exception("Failed loading MCP tools")
        return []