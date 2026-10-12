import hashlib
import json
import sqlite3
from collections.abc import Mapping, Sequence
from pathlib import Path


class EmbeddingCache:
	def __init__(self, path: Path, model_name: str) -> None:
		self._path = path
		self._model_name = model_name
		path.parent.mkdir(parents=True, exist_ok=True)
		with self._connect() as connection:
			connection.execute(
				"create table if not exists embeddings ("
				"cache_key text primary key, vector_json text not null)"
			)

	def keys_for(self, texts: Sequence[str]) -> list[str]:
		return [
			hashlib.sha256(f"{self._model_name}\0{text}".encode()).hexdigest()
			for text in texts
		]

	def get_many(self, keys: Sequence[str]) -> dict[str, list[float]]:
		if not keys:
			return {}
		found: dict[str, list[float]] = {}
		with self._connect() as connection:
			for start in range(0, len(keys), 900):
				subset = keys[start : start + 900]
				placeholders = ",".join("?" for _ in subset)
				rows = connection.execute(
					f"select cache_key, vector_json from embeddings where cache_key in ({placeholders})",
					subset,
				)
				found.update((key, json.loads(vector)) for key, vector in rows)
		return found

	def set_many(self, vectors: Mapping[str, Sequence[float]]) -> None:
		if not vectors:
			return
		with self._connect() as connection:
			connection.executemany(
				"insert into embeddings(cache_key, vector_json) values(?, ?) "
				"on conflict(cache_key) do update set vector_json=excluded.vector_json",
				[(key, json.dumps(list(vector))) for key, vector in vectors.items()],
			)

	def _connect(self) -> sqlite3.Connection:
		return sqlite3.connect(self._path, timeout=30)
