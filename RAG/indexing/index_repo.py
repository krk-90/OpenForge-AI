import hashlib
from pathlib import Path

from RAG.chunking.code_chunker import CodeChunker
from RAG.chunking.doc_chunker import MarkdownChunker
from RAG.chunking.issue_chunker import IssueChunker
from RAG.ingestion.github_client import GitHubClient
from RAG.ingestion.issue_loader import IssueLoader
from RAG.ingestion.pr_loader import PRLoader
from RAG.ingestion.repo_loader import RepoLoader, RepoSnapshot
from RAG.indexing.embedder import Embedder
from RAG.indexing.incremental_index import IncrementalIndexer
from RAG.models import Chunk

_CODE_SUFFIXES = {
	".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".go", ".rs",
	".java", ".c", ".h", ".cpp", ".hpp", ".cs", ".rb", ".php", ".swift",
	".kt", ".scala",
}
_DOC_NAMES = {"readme", "contributing", "code_of_conduct", "security", "changelog"}


class RepositoryIndexPipeline:
	def __init__(
		self,
		github: GitHubClient,
		cache_dir: Path,
		github_token: str | None,
		max_file_bytes: int,
		max_comments: int,
		code_chunker: CodeChunker,
		doc_chunker: MarkdownChunker,
		issue_chunker: IssueChunker,
		indexer: IncrementalIndexer,
	) -> None:
		self._github = github
		self._repo_loader = RepoLoader(github, cache_dir, github_token, max_file_bytes)
		self._issue_loader = IssueLoader(github, max_comments)
		self._pr_loader = PRLoader(github)
		self._code_chunker = code_chunker
		self._doc_chunker = doc_chunker
		self._issue_chunker = issue_chunker
		self._indexer = indexer

	def index(self, repo_url: str, branch: str | None = None) -> dict[str, object]:
		snapshot = self._repo_loader.load(repo_url, branch)
		chunks: list[Chunk] = []
		file_count = 0
		for file in snapshot.files:
			path = Path(file.path)
			suffix = path.suffix.casefold()
			name = path.stem.casefold().replace("-", "_")
			is_docs = suffix in {".md", ".rst", ".txt"} or any(
				segment.casefold() in {"docs", "doc", "issue_template", "issue_templates", "workflows"}
				for segment in path.parts
			) or name in _DOC_NAMES
			if suffix in _CODE_SUFFIXES:
				file_chunks = self._code_chunker.chunk(
					snapshot.repo_id, file.path, file.content,
					snapshot.commit_sha, file.content_hash,
				)
			elif is_docs:
				file_chunks = self._doc_chunker.chunk(
					snapshot.repo_id, file.path, file.content, snapshot.commit_sha,
					file.content_hash, self._file_chunk_type(file.path),
				)
			else:
				continue
			chunks.extend(file_chunks)
			file_count += 1

		issues = self._issue_loader.load(snapshot.repo_id)
		pull_requests = self._pr_loader.load(snapshot.repo_id)
		for issue in issues:
			chunks.extend(self._issue_chunker.chunk(snapshot.repo_id, issue, snapshot.commit_sha))
		for pull in pull_requests:
			text = f"Closed PR #{pull['pr_number']}: {pull['title']}\n\n{pull['body']}"
			symbol = f"pr:{pull['pr_number']}"
			chunk_id = hashlib.sha1(
				f"{snapshot.repo_id}\0{symbol}\0{snapshot.commit_sha}".encode()
			).hexdigest()
			chunks.append(Chunk(chunk_id, text, {
				"repo_id": snapshot.repo_id, "path": f"pulls/{pull['pr_number']}",
				"chunk_type": "past_pr", "pr_number": pull["pr_number"],
				"merged": pull["merged"], "url": pull["url"],
				"linked_issue_numbers": pull["linked_issue_numbers"],
				"changed_files": pull["changed_files"],
				"commit_sha": snapshot.commit_sha,
				"content_hash": hashlib.sha256(text.encode()).hexdigest(),
			}))

		indexed_count = self._indexer.index(chunks)
		return {
			"repo_id": snapshot.repo_id,
			"repo_url": snapshot.repo_url,
			"commit_sha": snapshot.commit_sha,
			"branch": branch or snapshot.default_branch,
			"files_indexed": file_count,
			"issues_indexed": len(issues),
			"pull_requests_indexed": len(pull_requests),
			"chunks_indexed": indexed_count,
		}

	@staticmethod
	def _file_chunk_type(path: str) -> str:
		lowered = path.casefold()
		if ".github/workflows/" in lowered:
			return "ci_config"
		if "issue_template" in lowered:
			return "issue_template"
		return "documentation"
