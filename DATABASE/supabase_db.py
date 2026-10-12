import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from supabase import Client, create_client


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

_client: Client | None = None


def get_supabase_client() -> Client:
	global _client
	if _client is None:
		url = os.getenv("SUPABASE_URL")
		service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
		if not url or not service_role_key:
			raise RuntimeError(
				"SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be configured"
			)
		_client = create_client(url, service_role_key)
	return _client


def save_generated_documentation(
	repository_name: str,
	document: str,
	output_format: str = "markdown",
) -> Any:
	return (
		get_supabase_client()
		.table("generated_docs")
		.upsert(
			{
				"repository_name": repository_name,
				"document": document,
				"output_format": output_format,
			},
			on_conflict="repository_name",
		)
		.execute()
	)


def get_generated_documentation(repository_name: str) -> dict | None:
	response = (
		get_supabase_client()
		.table("generated_docs")
		.select("document, output_format")
		.eq("repository_name", repository_name)
		.maybe_single()
		.execute()
	)
	return response.data if isinstance(response.data, dict) else None


def save_repository_search(query: str, repositories: list[dict]) -> Any:
	return (
		get_supabase_client()
		.table("repository_search_history")
		.insert(
			{
				"query": query,
				"result_count": len(repositories),
				"results": repositories,
			}
		)
		.execute()
	)
