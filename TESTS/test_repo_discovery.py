import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

project_root = str(Path(__file__).resolve().parents[1])
if project_root not in sys.path:
	sys.path.insert(0, project_root)

from Agents.issue_matcher.repo_discovery_engine import RepoDiscoveryAgent


class RepoDiscoveryAgentTests(unittest.IsolatedAsyncioTestCase):
	async def test_rerank_accepts_fenced_json_response(self):
		llm = SimpleNamespace(
			ainvoke=AsyncMock(return_value=SimpleNamespace(content='''```json
[
  {
    "repository": "acme/python-tools",
    "score": 91,
    "stars": 1200,
    "language": "Python",
    "reason": "Active project with approachable documentation work."
  }
]
```''')),
		)
		agent = RepoDiscoveryAgent(github_tools=[], user_id="user-1", llm=llm)

		result = await agent.rerank(
			[{"full_name": "acme/python-tools", "language": "Python"}],
			["Python"],
		)

		self.assertEqual(len(result), 1)
		self.assertEqual(result[0].repository, "acme/python-tools")
		self.assertEqual(result[0].score, 91)


if __name__ == "__main__":
	unittest.main()