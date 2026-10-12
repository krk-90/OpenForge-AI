import asyncio
import sys
from pathlib import Path

project_root = str(Path(__file__).resolve().parents[1])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from Agents.issue_matcher.repo_discovery_engine import RepoDiscoveryAgent
from MCP_server.server.github_git_server import get_openforge_tools


async def main():

    tools = await get_openforge_tools()

    agent = RepoDiscoveryAgent(
        github_tools=tools
    )

    result = await agent.discover(
        [
            "FastAPI",
            "LangGraph",
            "RAG",
            "Agents"
        ]
    )

    print(result)


if __name__ == "__main__":
    asyncio.run(main())