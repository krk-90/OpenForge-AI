from __future__ import annotations

import logging
import os
import shutil

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

logger = logging.getLogger(__name__)

_READ_ONLY_TOOLS = {
    "get_repository",
    "list_branches",
    "list_commits",
    "get_file_contents",
    "search_code",
    "search_repositories",
    "get_tree",
    "list_pull_requests",
    "get_pull_request",
    "get_pull_request_files",
    "list_issues",
    "get_issue",
    "get_me",
}


def _find_docker() -> str | None:
    return shutil.which("docker")


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
        docker_exe = _find_docker()

        if docker_exe:
            logger.info("GitHub MCP via Docker")

            server_configs["github"] = {
                "command": docker_exe,
                "args": [
                    "run",
                    "-i",
                    "--rm",
                    "-e",
                    f"GITHUB_PERSONAL_ACCESS_TOKEN={github_token}",
                    "ghcr.io/github/github-mcp-server",
                ],
                "transport": "stdio",
            }

        else:
            logger.info("GitHub MCP via NPX")

            server_configs["github"] = {
                "command": "npx",
                "args": [
                    "-y",
                    "@modelcontextprotocol/server-github",
                ],
                "env": {
                    "GITHUB_PERSONAL_ACCESS_TOKEN": github_token,
                },
                "transport": "stdio",
            }

    else:
        logger.warning("GITHUB_TOKEN missing")

    if not server_configs:
        logger.warning("No MCP servers available")
        return []

    try:
        client = MultiServerMCPClient(server_configs)

        tools = await client.get_tools()

        allow_write = (
            os.getenv(
                "GITHUB_MCP_ALLOW_WRITE",
                "false",
            ).lower()
            == "true"
        )

        filtered_tools = []

        for tool in tools:
            if tool.name in _READ_ONLY_TOOLS:
                filtered_tools.append(tool)
                continue

            if not tool.name.startswith("github"):
                filtered_tools.append(tool)
                continue

            if allow_write:
                filtered_tools.append(tool)

        unique_tools = {}
        for tool in filtered_tools:
            unique_tools[tool.name] = tool

        result = list(unique_tools.values())

        logger.info(
            "Loaded %d MCP tools",
            len(result),
        )

        for tool in result:
            logger.info("Tool: %s", tool.name)

        return result

    except Exception:
        logger.exception("Failed loading MCP tools")
        return []