from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any, Callable
from urllib.parse import urlsplit

from Agents.orchestrator.prompts import build_messages
from DATABASE.supabase_db import load_agent_memory, save_agent_memory

logger = logging.getLogger(__name__)


class OrchestratorAgent:
	"""Coordinate a grounded conversation and persist its per-session history."""

	def __init__(
		self,
		llm=None,
		*,
		memory_loader: Callable[..., list[dict[str, str]]] = load_agent_memory,
		memory_saver: Callable[..., Any] = save_agent_memory,
		github_tools: list[Any] | None = None,
		max_history_messages: int = 20,
	):
		if max_history_messages < 0:
			raise ValueError("max_history_messages must be non-negative")
		if llm is None:
			from langchain_groq import ChatGroq

			llm = ChatGroq(
				model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
				temperature=0,
			)
		self.llm = llm
		self.memory_loader = memory_loader
		self.memory_saver = memory_saver
		self.github_tools = github_tools or []
		self.max_history_messages = max_history_messages

	@staticmethod
	def _needs_issue_lookup(user_input: str) -> bool:
		words = set(re.findall(r"[a-z0-9-]+", user_input.casefold()))
		return bool(words & {"issue", "issues", "beginner", "beginner-friendly"}) or "good first" in user_input.casefold()

	@staticmethod
	def _repository_parts(repository_id: str) -> tuple[str, str] | None:
		url = repository_id if "://" in repository_id else f"https://github.com/{repository_id}"
		parts = [part for part in urlsplit(url).path.split("/") if part]
		if len(parts) < 2:
			return None
		return parts[0], parts[1].removesuffix(".git")

	@staticmethod
	def _supported_tool_arguments(tool: Any, arguments: dict[str, Any]) -> dict[str, Any]:
		schema = getattr(tool, "args_schema", None)
		if isinstance(schema, dict):
			fields = schema.get("properties", {})
		elif schema is not None:
			fields = getattr(schema, "model_fields", None) or getattr(schema, "__fields__", None)
		else:
			fields = None
		if fields:
			return {name: value for name, value in arguments.items() if name in fields}
		return arguments

	@classmethod
	def _decode_tool_result(cls, result: Any) -> Any:
		if isinstance(result, list):
			text_blocks = [
				item["text"] for item in result
				if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str)
			]
			if text_blocks:
				text = "\n".join(text_blocks)
				try:
					return json.loads(text)
				except json.JSONDecodeError:
					return text
			return result
		if isinstance(result, str):
			try:
				return json.loads(result)
			except json.JSONDecodeError:
				return result
		if isinstance(result, dict) and isinstance(result.get("content"), list):
			return cls._decode_tool_result(result["content"])
		return result

	async def _load_issue_context(self, user_input: str, repository_id: str) -> str | None:
		if not self._needs_issue_lookup(user_input):
			return ""
		tool = next((tool for tool in self.github_tools if tool.name == "list_issues"), None)
		repository = self._repository_parts(repository_id)
		if tool is None or repository is None:
			return None
		owner, repo = repository
		arguments = self._supported_tool_arguments(tool, {
			"owner": owner,
			"repo": repo,
			"state": "open",
			"perPage": 30,
		})
		try:
			result = self._decode_tool_result(await tool.ainvoke(arguments))
		except Exception:
			logger.exception("Could not fetch open issues for %s/%s", owner, repo)
			return None
		if isinstance(result, dict):
			result = result.get("issues", result.get("items", result.get("data", [])))
		if not isinstance(result, list):
			return None

		issues = []
		for issue in result[:30]:
			if not isinstance(issue, dict):
				continue
			labels = issue.get("labels", [])
			label_names = [
				label if isinstance(label, str) else label.get("name", "")
				for label in labels if isinstance(label, (str, dict))
			]
			issues.append({
				"number": issue.get("number"),
				"title": issue.get("title", ""),
				"labels": [label for label in label_names if label],
				"body": (issue.get("body") or "")[:1200],
				"url": issue.get("html_url") or issue.get("url", ""),
			})
		return json.dumps({"repository": f"{owner}/{repo}", "open_issues": issues}, ensure_ascii=False)

	async def run(
		self,
		user_input: str,
		user_id: str,
		session_id: str,
		repository_id: str,
		repository_context: str = "",
	) -> str:
		if not user_input.strip():
			raise ValueError("user_input is required")
		if not user_id.strip() or not session_id.strip() or not repository_id.strip():
			raise ValueError("user_id, session_id, and repository_id are required")

		history = await asyncio.to_thread(self.memory_loader, user_id, session_id)
		if not isinstance(history, list):
			raise TypeError("Agent memory must be a list of messages")
		history = history[-self.max_history_messages:] if self.max_history_messages else []
		issue_context = await self._load_issue_context(user_input, repository_id)
		if issue_context is None:
			answer = (
				f"I couldn't verify open issues for {repository_id}. GitHub issue lookup is unavailable; "
				"configure GitHub MCP and GITHUB_TOKEN, then retry. I won't recommend an unverified issue."
			)
			updated_history = [*history, {"role": "human", "content": user_input.strip()}]
			updated_history.append({"role": "ai", "content": answer})
			await asyncio.to_thread(
				self.memory_saver,
				user_id,
				session_id,
				repository_id,
				updated_history,
			)
			return answer
		if issue_context:
			repository_context = "\n\nOpen GitHub issue evidence:\n" + issue_context
		messages = build_messages(
			user_input,
			repository_id,
			repository_context,
			history,
		)
		response = await self.llm.ainvoke(messages)
		answer = response.content if hasattr(response, "content") else response
		if not isinstance(answer, str):
			raise TypeError("Orchestrator model returned a non-text response")
		if not answer.strip():
			raise RuntimeError("Orchestrator model returned an empty response")
		answer = answer.strip()

		updated_history = [*history, {"role": "human", "content": user_input.strip()}]
		updated_history.append({"role": "ai", "content": answer})
		await asyncio.to_thread(
			self.memory_saver,
			user_id,
			session_id,
			repository_id,
			updated_history,
		)
		return answer


__all__ = ["OrchestratorAgent"]