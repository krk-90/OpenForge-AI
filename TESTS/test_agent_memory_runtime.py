import sys
import unittest
from pathlib import Path

project_root = str(Path(__file__).resolve().parents[1])
if project_root not in sys.path:
	sys.path.insert(0, project_root)

from Agents.memory.agent_memory import AgentMemory
from Agents.memory.response_cache import AgentResponseCache


class AgentMemoryRuntimeTests(unittest.IsolatedAsyncioTestCase):
	async def test_memory_appends_agent_turn_and_bounds_history(self):
		stored = []
		memory = AgentMemory(
			loader=lambda _user, _session: [
				{"role": "human", "content": "older request"},
				{"role": "ai", "content": "older response"},
			],
			saver=lambda *args: stored.append(args),
			max_messages=2,
		)

		await memory.remember_turn(
			"user-1", "session-1", "acme/demo", "mentor",
			{"question": "Where do I begin?"}, {"first_task": "Read the route"},
		)

		self.assertEqual(len(stored[0][3]), 2)
		self.assertIn('"agent": "mentor"', stored[0][3][0]["content"])
		self.assertIn('"first_task": "Read the route"', stored[0][3][1]["content"])

	async def test_response_cache_reuses_a_user_scoped_result(self):
		saves = []
		calls = []
		cache = AgentResponseCache(
			loader=lambda _user_id, _key: None,
			saver=lambda *args: saves.append(args),
		)

		async def create_result():
			calls.append(True)
			return {"answer": "cached"}

		first = await cache.get_or_create("mentor", "user-1", {"q": "help"}, create_result)
		second = await cache.get_or_create("mentor", "user-1", {"q": "help"}, create_result)
		other_user = await cache.get_or_create("mentor", "user-2", {"q": "help"}, create_result)

		self.assertEqual(first, {"answer": "cached"})
		self.assertEqual(second, first)
		self.assertEqual(other_user, first)
		self.assertEqual(len(calls), 2)
		self.assertEqual(len(saves), 2)


if __name__ == "__main__":
	unittest.main()