from __future__ import annotations

import asyncio
import json
from typing import Any, Callable

from DATABASE.supabase_db import load_agent_memory, save_agent_memory


class AgentMemory:
	"""Store user/assistant turns shared across OpenForge agents."""

	def __init__(
		self,
		*,
		loader: Callable[..., list[dict[str, str]]] = load_agent_memory,
		saver: Callable[..., Any] = save_agent_memory,
		max_messages: int = 40,
	):
		if max_messages < 2:
			raise ValueError("max_messages must be at least 2")
		self.loader = loader
		self.saver = saver
		self.max_messages = max_messages

	async def load(self, user_id: str, session_id: str) -> list[dict[str, str]]:
		messages = await asyncio.to_thread(self.loader, user_id, session_id)
		if not isinstance(messages, list):
			raise TypeError("Agent memory must be a list of messages")
		return messages[-self.max_messages:]

	async def remember_turn(
		self,
		user_id: str,
		session_id: str,
		repository_id: str,
		agent_name: str,
		request_data: Any,
		response_data: Any,
	) -> None:
		messages = await self.load(user_id, session_id)
		request_text = json.dumps(
			{"agent": agent_name, "request": _json_value(request_data)},
			sort_keys=True,
		)
		response_text = json.dumps(_json_value(response_data), sort_keys=True)
		messages.extend([
			{"role": "human", "content": request_text},
			{"role": "ai", "content": response_text},
		])
		messages = messages[-self.max_messages:]
		await asyncio.to_thread(
			self.saver,
			user_id,
			session_id,
			repository_id,
			messages,
		)


def _json_value(value: Any) -> Any:
	if hasattr(value, "model_dump"):
		return value.model_dump(mode="json")
	return value