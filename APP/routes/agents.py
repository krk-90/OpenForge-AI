from __future__ import annotations

import asyncio
import logging
from typing import Annotated, Any
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

from Agents.memory.agent_memory import AgentMemory
from Agents.memory.response_cache import AgentResponseCache
from APP.core.security import bearer_scheme, get_authenticated_user_id
from DATABASE.supabase_db import (create_agent_chat_session,
                                  delete_agent_chat_session,
                                  get_agent_chat_session,
                                  get_developer_profile,
                                  get_repository_search_history,
                                  list_agent_chat_sessions,
                                  save_developer_profile)
from schemas.repo import DocAgentRequest

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agents", tags=["agents"])
agent_memory = AgentMemory()
agent_cache = AgentResponseCache()
_github_tools: list[Any] | None = None
_github_tools_lock = asyncio.Lock()


def current_user_id(
	credentials: Annotated[
		HTTPAuthorizationCredentials | None,
		Depends(bearer_scheme),
	],
) -> str:
	return get_authenticated_user_id(credentials)


CurrentUser = Annotated[str, Depends(current_user_id)]


async def get_github_tools() -> list[Any]:
	global _github_tools
	if _github_tools is None:
		async with _github_tools_lock:
			if _github_tools is None:
				try:
					from MCP_server.server.github_git_server import get_openforge_tools

					_github_tools = await get_openforge_tools()
				except Exception:
					logger.exception("Could not initialize GitHub MCP tools")
					_github_tools = []
	return _github_tools


GithubTools = Annotated[list[Any], Depends(get_github_tools)]


class OrchestratorRequest(BaseModel):
	message: str = Field(min_length=1, max_length=10000)
	session_id: str = Field(min_length=1, max_length=200)
	repository_id: str = Field(min_length=1, max_length=300)
	repository_context: str = Field(default="", max_length=30000)


class ChatSessionRequest(BaseModel):
	repository_id: str = Field(default="", max_length=300)
	title: str = Field(default="New chat", min_length=1, max_length=120)


class MentorRequest(OrchestratorRequest):
	profile: dict[str, Any] | None = None
	issue: dict[str, Any] | str | None = None


class ProfileRequest(BaseModel):
	session_id: str = Field(min_length=1, max_length=200)
	profile: dict[str, Any]


class PullRequestReviewRequest(BaseModel):
	session_id: str = Field(min_length=1, max_length=200)
	owner: str = Field(min_length=1, max_length=100)
	repo: str = Field(min_length=1, max_length=100)
	pull_number: int = Field(ge=1)
	diff: str | None = Field(default=None, max_length=100000)
	additional_context: str = Field(default="", max_length=20000)


class RagQuestionRequest(BaseModel):
	session_id: str = Field(min_length=1, max_length=200)
	repository_id: str = Field(min_length=1, max_length=300)
	question: str = Field(min_length=1, max_length=10000)
	limit: int = Field(default=6, ge=1, le=20)


class DocumentationRequest(BaseModel):
	session_id: str = Field(min_length=1, max_length=200)
	request: DocAgentRequest


class RepositoryDiscoveryRequest(BaseModel):
	session_id: str = Field(min_length=1, max_length=200)
	skills: list[str] = Field(min_length=1, max_length=30)


@router.get("")
def list_agents() -> dict[str, list[dict[str, str]]]:
	return {
		"agents": [
			{"name": "orchestrator", "endpoint": "/agents/orchestrator"},
			{"name": "mentor", "endpoint": "/agents/mentor"},
			{"name": "profile", "endpoint": "/agents/profile"},
			{"name": "pr-reviewer", "endpoint": "/agents/pr-review"},
			{"name": "repository-rag", "endpoint": "/agents/rag/query"},
			{"name": "documentation", "endpoint": "/agents/documentation"},
			{"name": "repository-discovery", "endpoint": "/agents/repository-discovery"},
		]
	}


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
async def create_chat_session(
	request: ChatSessionRequest,
	user_id: CurrentUser,
) -> dict[str, Any]:
	try:
		session = await asyncio.to_thread(
			create_agent_chat_session,
			user_id,
			request.repository_id,
			request.title.strip(),
		)
		return {"session": session}
	except Exception as exc:
		logger.exception("Could not create chat session")
		raise HTTPException(status_code=503, detail="Could not create chat session.") from exc


@router.get("/sessions")
async def list_chat_sessions(
	user_id: CurrentUser,
	limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, list[dict[str, Any]]]:
	try:
		sessions = await asyncio.to_thread(list_agent_chat_sessions, user_id, limit)
	except Exception as exc:
		logger.exception("Could not load chat sessions")
		raise HTTPException(status_code=503, detail="Could not load chat sessions.") from exc
	return {"sessions": sessions}


@router.get("/sessions/{session_id}")
async def read_chat_session(
	session_id: str,
	user_id: CurrentUser,
) -> dict[str, Any]:
	session = await _require_owned_session(user_id, session_id)
	try:
		messages = await agent_memory.load(user_id, session_id)
	except Exception as exc:
		logger.exception("Could not load chat history")
		raise HTTPException(status_code=503, detail="Could not load chat history.") from exc
	return {"session": session, "messages": messages}


@router.delete("/sessions/{session_id}")
async def remove_chat_session(
	session_id: str,
	user_id: CurrentUser,
) -> dict[str, bool]:
	await _require_owned_session(user_id, session_id)
	try:
		deleted = await asyncio.to_thread(delete_agent_chat_session, user_id, session_id)
	except Exception as exc:
		logger.exception("Could not delete chat session")
		raise HTTPException(status_code=503, detail="Could not delete chat session.") from exc
	return {"deleted": deleted}


async def _require_owned_session(user_id: str, session_id: str) -> dict[str, Any]:
	try:
		session = await asyncio.to_thread(get_agent_chat_session, user_id, session_id)
	except Exception as exc:
		logger.exception("Could not verify chat-session ownership")
		raise HTTPException(status_code=503, detail="Chat session storage is unavailable.") from exc
	if session is None:
		raise HTTPException(status_code=404, detail="Chat session not found.")
	return session


@router.get("/repository-discovery/history")
async def repository_discovery_history(
	user_id: CurrentUser,
	limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, list[dict[str, Any]]]:
	try:
		items = await asyncio.to_thread(get_repository_search_history, user_id, limit)
	except Exception as exc:
		logger.exception("Could not load repository search history")
		raise HTTPException(
			status_code=503,
			detail="Repository search history is unavailable.",
		) from exc
	return {"searches": items}


async def _remember(
	agent_name: str,
	user_id: str,
	session_id: str,
	repository_id: str,
	request_data: Any,
	response_data: Any,
) -> None:
	try:
		await agent_memory.remember_turn(
			user_id,
			session_id,
			repository_id,
			agent_name,
			request_data,
			response_data,
		)
	except Exception as exc:
		logger.exception("Could not persist %s conversation memory", agent_name)
		raise HTTPException(
			status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
			detail="Agent memory storage is unavailable.",
		) from exc


async def _cached(
	agent_name: str,
	user_id: str,
	payload: Any,
	factory,
) -> Any:
	return await agent_cache.get_or_create(agent_name, user_id, payload, factory)


@router.post("/orchestrator")
async def run_orchestrator(
	request: OrchestratorRequest,
	user_id: CurrentUser,
	github_tools: GithubTools,
) -> dict[str, str]:
	from Agents.orchestrator.orchestrator_agent import OrchestratorAgent

	await _require_owned_session(user_id, request.session_id)
	try:
		answer = await OrchestratorAgent(github_tools=github_tools).run(
			request.message,
			user_id,
			request.session_id,
			request.repository_id,
			request.repository_context,
		)
	except Exception as exc:
		logger.exception("Orchestrator request failed")
		raise HTTPException(status_code=502, detail="Orchestrator request failed.") from exc
	return {"answer": answer}


@router.post("/mentor")
async def run_mentor(
	request: MentorRequest,
	user_id: CurrentUser,
) -> dict[str, Any]:
	from Agents.mentor.mentor_agent import MentorAgent

	try:
		await _require_owned_session(user_id, request.session_id)
		history = await agent_memory.load(user_id, request.session_id)
		recent_history = history[-8:]
		cache_payload = {
			"request": request.model_dump(mode="json"),
			"history": recent_history,
		}
		issue = request.issue
		if recent_history:
			issue = {"current_issue": issue, "recent_conversation": recent_history}
		result = await _cached(
			"mentor",
			user_id,
			cache_payload,
			lambda: MentorAgent().mentor(
				request.message,
				request.repository_context,
				profile=request.profile,
				issue=issue,
			),
		)
		await _remember(
			"mentor", user_id, request.session_id, request.repository_id,
			request.model_dump(mode="json"), result,
		)
		return result
	except HTTPException:
		raise
	except Exception as exc:
		logger.exception("Mentor request failed")
		raise HTTPException(status_code=502, detail="Mentor request failed.") from exc


@router.post("/profile")
async def build_profile(
	request: ProfileRequest,
	user_id: CurrentUser,
) -> dict[str, Any]:
	await _require_owned_session(user_id, request.session_id)
	try:
		result = await _cached(
			"profile",
			user_id,
			request.profile,
			lambda: _build_profile_result(request.profile),
		)
	except ValueError as exc:
		raise HTTPException(status_code=422, detail="Profile data is invalid.") from exc
	except HTTPException:
		raise
	except Exception as exc:
		logger.exception("Profile processing failed")
		raise HTTPException(status_code=502, detail="Profile processing failed.") from exc

	try:
		await asyncio.to_thread(save_developer_profile, user_id, result["profile"])
		await _remember(
			"profile", user_id, request.session_id, "profile",
			request.profile, result,
		)
		return result
	except HTTPException:
		raise
	except Exception as exc:
		logger.exception("Could not persist developer profile")
		raise HTTPException(
			status_code=503,
			detail="Profile storage is unavailable.",
		) from exc


@router.get("/profile")
async def read_profile(user_id: CurrentUser) -> dict[str, Any]:
	try:
		profile = await asyncio.to_thread(get_developer_profile, user_id)
	except Exception as exc:
		logger.exception("Could not load developer profile")
		raise HTTPException(
			status_code=503,
			detail="Profile storage is unavailable.",
		) from exc
	if profile is None:
		raise HTTPException(status_code=404, detail="Developer profile not found.")
	return {"profile": profile}


async def _build_profile_result(profile_data: dict[str, Any]) -> dict[str, Any]:
	from Agents.profile.profile_agent import ProfileAgent

	profile = ProfileAgent().build_profile(profile_data)
	return {
		"profile": profile.model_dump(mode="json"),
		"discovery_terms": ProfileAgent.discovery_terms(profile),
	}


@router.post("/pr-review")
async def review_pull_request(
	request: PullRequestReviewRequest,
	user_id: CurrentUser,
) -> dict[str, Any]:
	await _require_owned_session(user_id, request.session_id)
	repository_id = f"{request.owner}/{request.repo}"
	payload = request.model_dump(mode="json")
	github_tools = [] if request.diff else await get_github_tools()
	if not request.diff and not github_tools:
		raise HTTPException(
			status_code=503,
			detail="GitHub MCP tools are not configured and no diff was supplied.",
		)
	try:
		result = await _cached(
			"pr-reviewer",
			user_id,
			payload,
			lambda: _review_result(request, github_tools),
		)
		await _remember(
			"pr-reviewer", user_id, request.session_id, repository_id, payload, result,
		)
		return result
	except HTTPException:
		raise
	except Exception as exc:
		logger.exception("Pull request review failed")
		raise HTTPException(status_code=422, detail="Pull request review failed.") from exc


async def _review_result(request: PullRequestReviewRequest, github_tools: list[Any]) -> dict[str, Any]:
	from Agents.PR_reviewer.pr_reviewer_agent import PRReviewerAgent

	result = await PRReviewerAgent(github_tools=github_tools).review(
		request.owner,
		request.repo,
		request.pull_number,
		diff=request.diff,
		additional_context=request.additional_context,
	)
	return result.model_dump(mode="json")


@router.post("/rag/query")
async def ask_repository(
	request: RagQuestionRequest,
	user_id: CurrentUser,
) -> dict[str, Any]:
	from Agents.RAG.openforge_ai import ask_codebase_question

	await _require_owned_session(user_id, request.session_id)
	payload = request.model_dump(mode="json")
	try:
		result = await _cached(
			"repository-rag",
			user_id,
			payload,
			lambda: ask_codebase_question(
				request.question,
				user_id,
				request.repository_id,
				request.limit,
			),
		)
		await _remember(
			"repository-rag", user_id, request.session_id,
			request.repository_id, payload, result,
		)
		return result
	except HTTPException:
		raise
	except Exception as exc:
		logger.exception("Repository question failed")
		raise HTTPException(status_code=503, detail="Repository RAG is unavailable.") from exc


@router.post("/documentation")
async def generate_documentation(
	request: DocumentationRequest,
	user_id: CurrentUser,
	github_tools: GithubTools,
) -> dict[str, str]:
	await _require_owned_session(user_id, request.session_id)
	if not github_tools:
		raise HTTPException(
			status_code=503,
			detail="GitHub MCP tools are not configured.",
		)
	repository_id = _documentation_repository_id(request.request)
	payload = request.model_dump(mode="json")
	try:
		result = await _cached(
			"documentation",
			user_id,
			payload,
			lambda: _documentation_result(request.request, github_tools, user_id),
		)
		await _remember(
			"documentation", user_id, request.session_id, repository_id, payload, result,
		)
		return {"document": result}
	except HTTPException:
		raise
	except Exception as exc:
		logger.exception("Documentation request failed")
		raise HTTPException(status_code=502, detail="Documentation request failed.") from exc


async def _documentation_result(
	request: DocAgentRequest,
	github_tools: list[Any],
	user_id: str,
) -> str:
	from Agents.documentation_agent import DocumentationAgent

	return await DocumentationAgent(github_tools=github_tools).run(request, user_id=user_id)


def _documentation_repository_id(request: DocAgentRequest) -> str:
	path = urlsplit(str(request.repository.repo_url)).path.strip("/")
	return path.removesuffix(".git")


@router.post("/repository-discovery")
async def discover_repositories(
	request: RepositoryDiscoveryRequest,
	user_id: CurrentUser,
	github_tools: GithubTools,
) -> dict[str, Any]:
	await _require_owned_session(user_id, request.session_id)
	if not github_tools:
		raise HTTPException(
			status_code=503,
			detail="GitHub MCP tools are not configured.",
		)
	payload = request.model_dump(mode="json")
	try:
		result = await _cached(
			"repository-discovery",
			user_id,
			payload,
			lambda: _discover_result(request.skills, github_tools, user_id),
		)
		await _remember(
			"repository-discovery", user_id, request.session_id,
			"repository-discovery", payload, result,
		)
		return {"repositories": result}
	except HTTPException:
		raise
	except Exception as exc:
		logger.exception("Repository discovery failed")
		raise HTTPException(status_code=502, detail="Repository discovery failed.") from exc


async def _discover_result(
	skills: list[str],
	github_tools: list[Any],
	user_id: str,
) -> list[dict[str, Any]]:
	from Agents.issue_matcher.repo_discovery_engine import RepoDiscoveryAgent

	recommendations = await RepoDiscoveryAgent(github_tools, user_id=user_id).discover(skills)
	return [item.model_dump(mode="json") for item in recommendations]