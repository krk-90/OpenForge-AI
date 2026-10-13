import inspect
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

project_root = str(Path(__file__).resolve().parents[1])
if project_root not in sys.path:
	sys.path.insert(0, project_root)

from fastapi.testclient import TestClient

from APP.main import app
from APP.routes import agents


class PassThroughCache:
	async def get_or_create(self, _name, _user_id, _payload, factory):
		result = factory()
		return await result if inspect.isawaitable(result) else result


class RecordingMemory:
	def __init__(self):
		self.turns = []

	async def remember_turn(self, *args):
		self.turns.append(args)

	async def load(self, _user_id, _session_id):
		return [{"role": "human", "content": "hello"}]


class AgentRouteTests(unittest.TestCase):
	def setUp(self):
		app.dependency_overrides.clear()
		app.dependency_overrides[agents.current_user_id] = lambda: "user-123"
		self.addCleanup(app.dependency_overrides.clear)
		self.session_lookup = patch.object(
			agents,
			"get_agent_chat_session",
			side_effect=lambda user_id, session_id: {
				"user_id": user_id,
				"session_id": session_id,
				"repository_id": "acme/demo",
				"title": "Test chat",
			},
		)
		self.session_lookup_mock = self.session_lookup.start()
		self.addCleanup(self.session_lookup.stop)
		self.original_cache = agents.agent_cache
		self.original_memory = agents.agent_memory
		agents.agent_cache = PassThroughCache()
		agents.agent_memory = RecordingMemory()
		self.addCleanup(setattr, agents, "agent_cache", self.original_cache)
		self.addCleanup(setattr, agents, "agent_memory", self.original_memory)
		self.saved_profiles = []
		profile_save = patch.object(
			agents,
			"save_developer_profile",
			side_effect=lambda *args: self.saved_profiles.append(args),
		)
		profile_save.start()
		self.addCleanup(profile_save.stop)
		self.client = TestClient(app)

	def test_catalog_lists_all_agent_endpoints(self):
		response = self.client.get("/agents")

		self.assertEqual(response.status_code, 200)
		self.assertEqual(
			{item["name"] for item in response.json()["agents"]},
			{
				"orchestrator",
				"mentor",
				"profile",
				"pr-reviewer",
				"repository-rag",
				"documentation",
				"repository-discovery",
			},
		)

	def test_profile_endpoint_uses_cache_and_shared_memory(self):
		response = self.client.post(
			"/agents/profile",
			json={
				"session_id": "session-1",
				"profile": {"skills": "Python, FastAPI", "interests": "fastapi, OSS"},
			},
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(
			response.json()["discovery_terms"],
			["Python", "FastAPI", "OSS"],
		)
		self.assertEqual(len(agents.agent_memory.turns), 1)
		self.assertEqual(self.saved_profiles[0][0], "user-123")
		self.assertEqual(self.saved_profiles[0][1]["skills"], ["Python", "FastAPI"])
		self.assertEqual(agents.agent_memory.turns[0][:4], (
			"user-123", "session-1", "profile", "profile"
		))

	def test_agent_routes_require_authentication(self):
		app.dependency_overrides.clear()
		response = TestClient(app).post(
			"/agents/profile",
			json={"session_id": "session-1", "profile": {}},
		)

		self.assertEqual(response.status_code, 401)

	def test_github_agents_return_service_unavailable_without_mcp_tools(self):
		app.dependency_overrides[agents.get_github_tools] = lambda: []
		documentation = self.client.post(
			"/agents/documentation",
			json={
				"session_id": "session-1",
				"request": {
					"repository": {"repo_url": "https://github.com/acme/demo"},
					"explanation_type": "repository",
				},
			},
		)
		discovery = self.client.post(
			"/agents/repository-discovery",
			json={"session_id": "session-1", "skills": ["Python"]},
		)

		self.assertEqual(documentation.status_code, 503)
		self.assertEqual(discovery.status_code, 503)

	def test_profile_read_returns_persisted_profile(self):
		with patch.object(
			agents,
			"get_developer_profile",
			return_value={"display_name": "Ada", "skills": ["Python"]},
		):
			response = self.client.get("/agents/profile")

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json()["profile"]["display_name"], "Ada")

	def test_search_history_endpoint_returns_user_scoped_rows(self):
		with patch.object(
			agents,
			"get_repository_search_history",
			return_value=[{"query": "Python", "result_count": 2}],
		) as history_loader:
			response = self.client.get("/agents/repository-discovery/history?limit=10")

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json()["searches"][0]["query"], "Python")
		history_loader.assert_called_once_with("user-123", 10)

	def test_create_session_returns_owner_scoped_session_id(self):
		session = {
			"user_id": "user-123",
			"session_id": "session-created",
			"repository_id": "acme/demo",
			"title": "OpenForge task",
		}
		with patch.object(agents, "create_agent_chat_session", return_value=session) as creator:
			response = self.client.post(
				"/agents/sessions",
				json={"repository_id": "acme/demo", "title": "OpenForge task"},
			)

		self.assertEqual(response.status_code, 201)
		self.assertEqual(response.json()["session"]["session_id"], "session-created")
		creator.assert_called_once_with("user-123", "acme/demo", "OpenForge task")

	def test_create_session_allows_repository_discovery_without_repository(self):
		session = {
			"user_id": "user-123",
			"session_id": "discovery-session",
			"repository_id": "",
			"title": "Find Python repositories",
		}
		with patch.object(agents, "create_agent_chat_session", return_value=session) as creator:
			response = self.client.post(
				"/agents/sessions",
				json={"repository_id": "", "title": "Find Python repositories"},
			)

		self.assertEqual(response.status_code, 201)
		self.assertEqual(response.json()["session"]["repository_id"], "")
		creator.assert_called_once_with("user-123", "", "Find Python repositories")

	def test_agent_rejects_session_not_owned_by_current_user(self):
		with patch.object(agents, "get_agent_chat_session", return_value=None):
			response = self.client.post(
				"/agents/profile",
				json={"session_id": "someone-elses-session", "profile": {}},
			)

		self.assertEqual(response.status_code, 404)

	def test_list_sessions_is_scoped_to_authenticated_user(self):
		with patch.object(
			agents,
			"list_agent_chat_sessions",
			return_value=[{"session_id": "session-1", "title": "My chat"}],
		) as session_lister:
			response = self.client.get("/agents/sessions")

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json()["sessions"][0]["session_id"], "session-1")
		session_lister.assert_called_once_with("user-123", 50)

	def test_read_session_returns_only_its_transcript(self):
		response = self.client.get("/agents/sessions/session-1")

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json()["messages"][0]["content"], "hello")
		self.session_lookup_mock.assert_called_with("user-123", "session-1")

	def test_orchestrator_receives_github_tools(self):
		github_tools = [object()]
		app.dependency_overrides[agents.get_github_tools] = lambda: github_tools
		with patch("Agents.orchestrator.orchestrator_agent.OrchestratorAgent") as orchestrator:
			orchestrator.return_value.run = AsyncMock(return_value="Grounded answer")
			response = self.client.post(
				"/agents/orchestrator",
				json={
					"message": "Find a good first issue",
					"session_id": "session-1",
					"repository_id": "acme/demo",
				},
			)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json()["answer"], "Grounded answer")
		orchestrator.assert_called_once_with(github_tools=github_tools)

	def test_delete_session_is_scoped_to_authenticated_user(self):
		with patch.object(agents, "delete_agent_chat_session", return_value=True) as deleter:
			response = self.client.delete("/agents/sessions/session-1")

		self.assertEqual(response.status_code, 200)
		self.assertTrue(response.json()["deleted"])
		deleter.assert_called_once_with("user-123", "session-1")


if __name__ == "__main__":
	unittest.main()