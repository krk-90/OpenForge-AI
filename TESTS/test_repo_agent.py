import asyncio
import json
import os
import sys
from pathlib import Path

project_root = str(Path(__file__).resolve().parents[1])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from Agents.issue_matcher.repo_discovery_engine import RepoDiscoveryAgent
from MCP_server.server.github_git_server import get_openforge_tools


async def main():
    user_id = os.getenv("OPENFORGE_USER_ID")
    if not user_id:
        raise RuntimeError("Set OPENFORGE_USER_ID to a Supabase Auth user UUID")

    tools = await get_openforge_tools()

    agent = RepoDiscoveryAgent(
        github_tools=tools,
        user_id=user_id,
    )

    result = await agent.discover(
        [
            "FastAPI",
            "LangGraph",
            "RAG",
            "Agents"
        ]
    )

    print(
        json.dumps(
            [recommendation.model_dump() for recommendation in result],
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())