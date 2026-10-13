import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

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
	user_id: str,
	repository_name: str,
	document: str,
	output_format: str = "markdown",
) -> Any:
	return (
		get_supabase_client()
		.table("generated_docs")
		.upsert(
			{
				"user_id": user_id,
				"repository_name": repository_name,
				"document": document,
				"output_format": output_format,
			},
			on_conflict="user_id,repository_name",
		)
		.execute()
	)


def get_generated_documentation(user_id: str, repository_name: str) -> dict | None:
	response = (
		get_supabase_client()
		.table("generated_docs")
		.select("document, output_format")
		.eq("user_id", user_id)
		.eq("repository_name", repository_name)
		.maybe_single()
		.execute()
	)
	return response.data if isinstance(response.data, dict) else None



def save_repository_search(
	query: str,
	repositories: list[dict],
	user_id: str,
) -> Any:
	payload = {
		"query": query,
		"result_count": len(repositories),
		"results": repositories,
	}
	payload["user_id"] = user_id
	return (
		get_supabase_client()
		.table("repository_search_history")
		.insert(payload)
		.execute()
	)


def get_repository_search_history(user_id: str, limit: int = 20) -> list[dict[str, Any]]:
	if limit < 1 or limit > 100:
		raise ValueError("limit must be between 1 and 100")
	response = (
		get_supabase_client()
		.table("repository_search_history")
		.select("id, query, result_count, results, searched_at")
		.eq("user_id", user_id)
		.order("searched_at", desc=True)
		.limit(limit)
		.execute()
	)
	return [row for row in (response.data or []) if isinstance(row, dict)]


def get_developer_profile(user_id: str) -> dict | None:
	response = (
		get_supabase_client()
		.table("developer_profiles")
		.select(
			"display_name, github_username, bio, skills, interests, "
			"preferred_languages, experience_level, contribution_goals, updated_at"
		)
		.eq("user_id", user_id)
		.maybe_single()
		.execute()
	)
	return response.data if isinstance(response.data, dict) else None


def save_developer_profile(user_id: str, profile: dict[str, Any]) -> Any:
	fields = (
		"display_name",
		"github_username",
		"bio",
		"skills",
		"interests",
		"preferred_languages",
		"experience_level",
		"contribution_goals",
	)
	payload = {field: profile[field] for field in fields if field in profile}
	payload["user_id"] = user_id
	payload["updated_at"] = datetime.now(timezone.utc).isoformat()
	return (
		get_supabase_client()
		.table("developer_profiles")
		.upsert(payload, on_conflict="user_id")
		.execute()
	)


def create_agent_chat_session(
	user_id: str,
	repository_id: str = "",
	title: str = "New chat",
) -> dict[str, Any]:
	payload = {
		"user_id": user_id,
		"session_id": str(uuid4()),
		"repository_id": repository_id,
		"title": title,
	}
	response = get_supabase_client().table("agent_chat_sessions").insert(payload).execute()
	if isinstance(response.data, list) and response.data and isinstance(response.data[0], dict):
		return response.data[0]
	return payload


def list_agent_chat_sessions(user_id: str, limit: int = 50) -> list[dict[str, Any]]:
	if limit < 1 or limit > 100:
		raise ValueError("limit must be between 1 and 100")
	response = (
		get_supabase_client()
		.table("agent_chat_sessions")
		.select("session_id, repository_id, title, created_at, updated_at")
		.eq("user_id", user_id)
		.order("updated_at", desc=True)
		.limit(limit)
		.execute()
	)
	return [row for row in (response.data or []) if isinstance(row, dict)]


def get_agent_chat_session(user_id: str, session_id: str) -> dict[str, Any] | None:
	response = (
		get_supabase_client()
		.table("agent_chat_sessions")
		.select("session_id, repository_id, title, created_at, updated_at")
		.eq("user_id", user_id)
		.eq("session_id", session_id)
		.maybe_single()
		.execute()
	)
	return response.data if isinstance(response.data, dict) else None


def delete_agent_chat_session(user_id: str, session_id: str) -> bool:
	client = get_supabase_client()
	(
		client.table("agent_conversation_memory")
		.delete()
		.eq("user_id", user_id)
		.eq("session_id", session_id)
		.execute()
	)
	response = (
		client.table("agent_chat_sessions")
		.delete()
		.eq("user_id", user_id)
		.eq("session_id", session_id)
		.execute()
	)
	return True


def load_agent_memory(user_id: str, session_id: str) -> list[dict[str, str]]:
	response = (
		get_supabase_client()
		.table("agent_conversation_memory")
		.select("messages")
		.eq("user_id", user_id)
		.eq("session_id", session_id)
		.maybe_single()
		.execute()
	)
	if response is None:
		return []
	data = response.data
	if not isinstance(data, dict) or not isinstance(data.get("messages"), list):
		return []
	return [
		message
		for message in data["messages"]
		if isinstance(message, dict)
		and message.get("role") in {"human", "ai"}
		and isinstance(message.get("content"), str)
	]


def save_agent_memory(
	user_id: str,
	session_id: str,
	repository_id: str,
	messages: list[dict[str, str]],
) -> Any:
	client = get_supabase_client()
	updated_at = datetime.now(timezone.utc).isoformat()
	client.table("agent_chat_sessions").upsert(
		{
			"user_id": user_id,
			"session_id": session_id,
			"repository_id": repository_id,
			"updated_at": updated_at,
		},
		on_conflict="user_id,session_id",
	).execute()
	return (
		client
		.table("agent_conversation_memory")
		.upsert(
			{
				"user_id": user_id,
				"session_id": session_id,
				"repository_id": repository_id,
				"messages": messages,
				"updated_at": updated_at,
			},
			on_conflict="user_id,session_id",
		)
		.execute()
	)


def load_agent_response_cache(user_id: str, cache_key: str) -> Any | None:
	response = (
		get_supabase_client()
		.table("agent_response_cache")
		.select("response, expires_at")
		.eq("user_id", user_id)
		.eq("cache_key", cache_key)
		.maybe_single()
		.execute()
	)
	data = response.data
	if not isinstance(data, dict) or not isinstance(data.get("response"), (dict, list, str, int, float, bool)):
		return None
	expires_at = data.get("expires_at")
	if isinstance(expires_at, str):
		try:
			if datetime.fromisoformat(expires_at.replace("Z", "+00:00")) <= datetime.now(timezone.utc):
				return None
		except ValueError:
			return None
	return data["response"]


def save_agent_response_cache(
	user_id: str,
	cache_key: str,
	agent_name: str,
	response: Any,
	ttl_seconds: int = 300,
) -> Any:
	now = datetime.now(timezone.utc)
	return (
		get_supabase_client()
		.table("agent_response_cache")
		.upsert(
			{
				"user_id": user_id,
				"cache_key": cache_key,
				"agent_name": agent_name,
				"response": response,
				"expires_at": (now + timedelta(seconds=ttl_seconds)).isoformat(),
				"updated_at": now.isoformat(),
			},
			on_conflict="cache_key",
		)
		.execute()
	)
