from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import threading
import time
from collections import OrderedDict
from typing import Any, Awaitable, Callable

from DATABASE.supabase_db import (load_agent_response_cache,
                                  save_agent_response_cache)

logger = logging.getLogger(__name__)
_MISS = object()


class AgentResponseCache:
	"""User-scoped TTL cache with an in-process front and Supabase backing."""

	def __init__(
		self,
		*,
		ttl_seconds: int = 300,
		max_entries: int = 256,
		loader: Callable[..., Any] = load_agent_response_cache,
		saver: Callable[..., Any] = save_agent_response_cache,
	):
		if ttl_seconds <= 0 or max_entries <= 0:
			raise ValueError("ttl_seconds and max_entries must be positive")
		self.ttl_seconds = ttl_seconds
		self.max_entries = max_entries
		self.loader = loader
		self.saver = saver
		self._entries: OrderedDict[str, tuple[float, Any]] = OrderedDict()
		self._lock = threading.RLock()

	@staticmethod
	def make_key(agent_name: str, user_id: str, payload: Any) -> str:
		if hasattr(payload, "model_dump"):
			payload = payload.model_dump(mode="json")
		canonical = json.dumps(
			{"agent": agent_name, "user_id": user_id, "payload": payload},
			sort_keys=True,
			separators=(",", ":"),
			default=str,
		)
		return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

	async def get_or_create(
		self,
		agent_name: str,
		user_id: str,
		payload: Any,
		factory: Callable[[], Awaitable[Any]],
	) -> Any:
		cache_key = self.make_key(agent_name, user_id, payload)
		cached = self._get_local(cache_key)
		if cached is not _MISS:
			return cached

		try:
			cached = await asyncio.to_thread(self.loader, user_id, cache_key)
		except Exception:
			logger.warning("Supabase response-cache lookup failed", exc_info=True)
			cached = None
		if cached is not None:
			self._put_local(cache_key, cached)
			return cached

		result = factory()
		if hasattr(result, "__await__"):
			result = await result
		if hasattr(result, "model_dump"):
			result = result.model_dump(mode="json")
		self._put_local(cache_key, result)
		try:
			await asyncio.to_thread(
				self.saver,
				user_id,
				cache_key,
				agent_name,
				result,
				self.ttl_seconds,
			)
		except Exception:
			logger.warning("Supabase response-cache write failed", exc_info=True)
		return result

	def _get_local(self, cache_key: str) -> Any:
		with self._lock:
			entry = self._entries.get(cache_key)
			if entry is None:
				return _MISS
			expires_at, value = entry
			if expires_at <= time.monotonic():
				self._entries.pop(cache_key, None)
				return _MISS
			self._entries.move_to_end(cache_key)
			return value

	def _put_local(self, cache_key: str, value: Any) -> None:
		with self._lock:
			self._entries[cache_key] = (time.monotonic() + self.ttl_seconds, value)
			self._entries.move_to_end(cache_key)
			while len(self._entries) > self.max_entries:
				self._entries.popitem(last=False)