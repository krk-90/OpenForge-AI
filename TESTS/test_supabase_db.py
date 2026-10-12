import sys
import unittest
from pathlib import Path
from unittest.mock import patch

project_root = str(Path(__file__).resolve().parents[1])
if project_root not in sys.path:
	sys.path.insert(0, project_root)

from DATABASE.supabase_db import (
	get_generated_documentation,
	save_generated_documentation,
	save_repository_search,
)


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

	def upsert(self, payload, **options):
		self.operation = "upsert"
		self.payload = payload
		self.options = options
		return self

	def insert(self, payload):
		self.operation = "insert"
		self.payload = payload
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
		save_generated_documentation("acme/demo", "# demo", "markdown")

		self.assertEqual(self.client.table_name, "generated_docs")
		self.assertEqual(self.client.query.operation, "upsert")
		self.assertEqual(self.client.query.options, {"on_conflict": "repository_name"})
		self.assertEqual(self.client.query.payload["document"], "# demo")

	def test_repository_search_stores_query_and_results(self):
		repositories = [{"full_name": "acme/demo"}]
		save_repository_search("FastAPI", repositories)

		self.assertEqual(self.client.table_name, "repository_search_history")
		self.assertEqual(self.client.query.operation, "insert")
		self.assertEqual(self.client.query.payload["query"], "FastAPI")
		self.assertEqual(self.client.query.payload["result_count"], 1)
		self.assertEqual(self.client.query.payload["results"], repositories)

	def test_generated_documentation_can_be_retrieved_by_repository(self):
		self.client.query.data = {"document": "# demo", "output_format": "markdown"}

		result = get_generated_documentation("acme/demo")

		self.assertEqual(self.client.table_name, "generated_docs")
		self.assertEqual(self.client.query.operation, "select")
		self.assertEqual(self.client.query.payload, "document, output_format")
		self.assertEqual(self.client.query.filters, [("repository_name", "acme/demo")])
		self.assertEqual(result, self.client.query.data)


if __name__ == "__main__":
	unittest.main()