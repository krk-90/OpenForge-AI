import hashlib
from collections.abc import Mapping

from RAG.models import Chunk


def stable_chunk_id(repo_id: str, path: str, symbol: str, commit_sha: str) -> str:
	identity = "\0".join((repo_id.casefold(), path, symbol, commit_sha))
	return hashlib.sha1(identity.encode("utf-8")).hexdigest()


def make_chunk(
	repo_id: str,
	path: str,
	symbol: str,
	commit_sha: str,
	text: str,
	metadata: Mapping[str, object],
) -> Chunk:
	return Chunk(
		id=stable_chunk_id(repo_id, path, symbol, commit_sha),
		text=text,
		metadata={
			"repo_id": repo_id.casefold(),
			"path": path,
			"symbol_name": symbol,
			"commit_sha": commit_sha,
			**metadata,
		},
	)
