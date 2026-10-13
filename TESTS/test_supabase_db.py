import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

project_root = str(Path(__file__).resolve().parents[1])
if project_root not in sys.path:
	sys.path.insert(0, project_root)

from DATABASE.supabase_db import (create_agent_chat_session,
                                  delete_agent_chat_session,
                                  get_agent_chat_session,
                                  get_developer_profile,
                                  get_generated_documentation,
                                  get_repository_search_history,
                                  list_agent_chat_sessions, load_agent_memory,
                                  load_agent_response_cache, save_agent_memory,
                                  save_agent_response_cache,
                                  save_developer_profile,
                                  save_generated_documentation,
                                  save_repository_search)


class FakeQuery:
	def __init__(self):
		self.operation = None
		self.payload = None
		self.options = None
		self.filters = []
		self.data = None

	def select(self, columns):
		self.operation = "select"
		self.payload = columns
		return self

	def eq(self, column, value):
		self.filters.append((column, value))
		return self

	def maybe_single(self):
		return self

	def order(self, column, **options):
		self.ordering = (column, options)
		return self

	def limit(self, count):
		self.limit_count = count
		return self

	def upsert(self, payload, **options):
		self.operation = "upsert"
		self.payload = payload
		self.options = options
		return self

	def insert(self, payload):
		self.operation = "insert"
		self.payload = payload
		return self

	def delete(self):
		self.operation = "delete"
		return self

	def execute(self):
		return self


class FakeClient:
	def __init__(self):
		self.query = FakeQuery()
		self.table_name = None

	def table(self, name):
		self.table_name = name
		return self.query


class SupabaseStorageTests(unittest.TestCase):
	def setUp(self):
		self.client = FakeClient()
		self.client_patch = patch(
			"DATABASE.supabase_db.get_supabase_client",
			return_value=self.client,
		)
		self.client_patch.start()
		self.addCleanup(self.client_patch.stop)

	def test_generated_documentation_is_upserted_by_repository(self):
		save_generated_documentation("user-123", "acme/demo", "# demo", "markdown")

		self.assertEqual(self.client.table_name, "generated_docs")
		self.assertEqual(self.client.query.operation, "upsert")
		self.assertEqual(
			self.client.query.options,
			{"on_conflict": "user_id,repository_name"},
		)
		self.assertEqual(self.client.query.payload["user_id"], "user-123")
		self.assertEqual(self.client.query.payload["document"], "# demo")

	def test_repository_search_stores_query_and_results(self):
		repositories = [{"full_name": "acme/demo"}]
		save_repository_search("FastAPI", repositories, user_id="user-123")

		self.assertEqual(self.client.table_name, "repository_search_history")
		self.assertEqual(self.client.query.operation, "insert")
		self.assertEqual(self.client.query.payload["query"], "FastAPI")
		self.assertEqual(self.client.query.payload["user_id"], "user-123")
		self.assertEqual(self.client.query.payload["result_count"], 1)
		self.assertEqual(self.client.query.payload["results"], repositories)

	def test_repository_search_history_is_scoped_to_user(self):
		repositories = [{"full_name": "acme/demo"}]

		save_repository_search("FastAPI", repositories, user_id="user-123")

		self.assertEqual(self.client.query.payload["user_id"], "user-123")

	def test_repository_search_history_can_be_read_for_user(self):
		rows = [{"query": "FastAPI", "result_count": 1}]
		self.client.query.data = rows

		result = get_repository_search_history("user-123", 10)

		self.assertEqual(self.client.query.filters, [("user_id", "user-123")])
		self.assertEqual(self.client.query.ordering, ("searched_at", {"desc": True}))
		self.assertEqual(self.client.query.limit_count, 10)
		self.assertEqual(result, rows)

	def test_developer_profile_is_upserted_by_user(self):
		profile = {"display_name": "Ada", "skills": ["Python"]}

		save_developer_profile("user-123", profile)

		self.assertEqual(self.client.table_name, "developer_profiles")
		self.assertEqual(self.client.query.operation, "upsert")
		self.assertEqual(self.client.query.options, {"on_conflict": "user_id"})
		self.assertEqual(self.client.query.payload["user_id"], "user-123")
		self.assertEqual(self.client.query.payload["skills"], ["Python"])

	def test_developer_profile_is_retrieved_by_user(self):
		self.client.query.data = {"display_name": "Ada", "skills": ["Python"]}

		profile = get_developer_profile("user-123")

		self.assertEqual(self.client.table_name, "developer_profiles")
		self.assertEqual(self.client.query.filters, [("user_id", "user-123")])
		self.assertEqual(profile, self.client.query.data)

	def test_chat_session_is_created_for_the_authenticated_user(self):
		session = create_agent_chat_session("user-123", "acme/demo", "Review issue")

		self.assertEqual(self.client.table_name, "agent_chat_sessions")
		self.assertEqual(self.client.query.operation, "insert")
		self.assertEqual(self.client.query.payload["user_id"], "user-123")
		self.assertEqual(self.client.query.payload["repository_id"], "acme/demo")
		self.assertEqual(session["session_id"], self.client.query.payload["session_id"])

	def test_chat_session_lookup_is_scoped_to_owner(self):
		self.client.query.data = {"session_id": "session-1", "title": "My chat"}

		session = get_agent_chat_session("user-123", "session-1")

		self.assertEqual(self.client.query.filters[-2:], [
			("user_id", "user-123"), ("session_id", "session-1")
		])
		self.assertEqual(session, self.client.query.data)

	def test_chat_session_list_is_scoped_to_owner(self):
		self.client.query.data = [{"session_id": "session-1"}]

		sessions = list_agent_chat_sessions("user-123", 10)

		self.assertEqual(self.client.query.filters, [("user_id", "user-123")])
		self.assertEqual(self.client.query.limit_count, 10)
		self.assertEqual(sessions, self.client.query.data)

	def test_chat_session_deletion_is_scoped_to_owner(self):
		deleted = delete_agent_chat_session("user-123", "session-1")

		self.assertTrue(deleted)
		self.assertEqual(self.client.table_name, "agent_chat_sessions")
		self.assertEqual(self.client.query.operation, "delete")
		self.assertEqual(self.client.query.filters[-2:], [
			("user_id", "user-123"), ("session_id", "session-1")
		])

	def test_generated_documentation_can_be_retrieved_by_repository(self):
		self.client.query.data = {"document": "# demo", "output_format": "markdown"}

		result = get_generated_documentation("user-123", "acme/demo")

		self.assertEqual(self.client.table_name, "generated_docs")
		self.assertEqual(self.client.query.operation, "select")
		self.assertEqual(self.client.query.payload, "document, output_format")
		self.assertEqual(
			self.client.query.filters,
			[("user_id", "user-123"), ("repository_name", "acme/demo")],
		)
		self.assertEqual(result, self.client.query.data)

	def test_agent_memory_is_upserted_per_user_and_session(self):
		messages = [{"role": "human", "content": "Help me start"}]

		save_agent_memory("user-1", "session-1", "acme/demo", messages)

		self.assertEqual(self.client.table_name, "agent_conversation_memory")
		self.assertEqual(self.client.query.operation, "upsert")
		self.assertEqual(
			self.client.query.options,
			{"on_conflict": "user_id,session_id"},
		)
		self.assertEqual(self.client.query.payload["messages"], messages)

	def test_agent_memory_load_is_scoped_to_user_and_session(self):
		messages = [{"role": "ai", "content": "Start with a focused test."}]
		self.client.query.data = {"messages": messages}

		result = load_agent_memory("user-1", "session-1")

		self.assertEqual(self.client.table_name, "agent_conversation_memory")
		self.assertEqual(self.client.query.operation, "select")
		self.assertEqual(
			self.client.query.filters,
			[("user_id", "user-1"), ("session_id", "session-1")],
		)
		self.assertEqual(result, messages)

	def test_agent_memory_load_returns_empty_when_query_has_no_response(self):
		with patch.object(self.client.query, "execute", return_value=None):
			result = load_agent_memory("user-1", "session-1")

		self.assertEqual(result, [])

	def test_agent_response_cache_is_upserted_with_expiration(self):
		response = {"answer": "cached result"}

		save_agent_response_cache("user-123", "cache-hash", "mentor", response, 120)

		self.assertEqual(self.client.table_name, "agent_response_cache")
		self.assertEqual(self.client.query.operation, "upsert")
		self.assertEqual(self.client.query.options, {"on_conflict": "cache_key"})
		self.assertEqual(self.client.query.payload["user_id"], "user-123")
		self.assertEqual(self.client.query.payload["response"], response)
		self.assertEqual(self.client.query.payload["agent_name"], "mentor")

	def test_agent_response_cache_load_ignores_expired_rows(self):
		self.client.query.data = {
			"response": {"answer": "stale"},
			"expires_at": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
		}

		result = load_agent_response_cache("user-123", "cache-hash")

		self.assertEqual(self.client.table_name, "agent_response_cache")
		self.assertIsNone(result)


if __name__ == "__main__":
	unittest.main()