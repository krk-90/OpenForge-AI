import ast
import hashlib
import re
from collections.abc import Callable
from pathlib import PurePosixPath

from RAG.chunking.chunk_metadata import make_chunk
from RAG.models import Chunk

_LANGUAGES = {
	".py": "python", ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript",
	".cjs": "javascript", ".ts": "typescript", ".tsx": "tsx", ".go": "go",
	".rs": "rust", ".java": "java", ".c": "c", ".h": "c", ".cpp": "cpp",
	".hpp": "cpp", ".cs": "c_sharp", ".rb": "ruby", ".php": "php",
	".swift": "swift", ".kt": "kotlin", ".scala": "scala",
}
_SYMBOL_TYPES = {
	"function_definition": "function", "method_definition": "method",
	"class_definition": "class", "function_declaration": "function",
	"class_declaration": "class", "method_declaration": "method",
	"function_item": "function", "impl_item": "class", "struct_item": "class",
}


class CodeChunker:
	def __init__(self, window_tokens: int = 800, overlap_tokens: int = 100,
				 summary: Callable[[str], str] | None = None) -> None:
		if window_tokens < 1 or not 0 <= overlap_tokens < window_tokens:
			raise ValueError("overlap_tokens must be non-negative and smaller than window_tokens")
		self._window_tokens = window_tokens
		self._overlap_tokens = overlap_tokens
		self._summary = summary

	def chunk(self, repo_id: str, path: str, content: str, commit_sha: str,
			  content_hash: str | None = None) -> list[Chunk]:
		language = _LANGUAGES.get(PurePosixPath(path).suffix.casefold())
		if language == "python":
			try:
				chunks = self._python_chunks(repo_id, path, content, commit_sha, content_hash)
			except SyntaxError:
				chunks = []
		elif language:
			chunks = self._tree_sitter_chunks(repo_id, path, content, commit_sha, language, content_hash)
		else:
			chunks = []
		return chunks or self._fallback(repo_id, path, content, commit_sha, content_hash, language or "text")

	def _python_chunks(self, repo_id: str, path: str, content: str, commit_sha: str,
					   content_hash: str | None) -> list[Chunk]:
		tree = ast.parse(content)
		lines = content.splitlines()
		imports = "\n".join(
			line for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))
			for line in lines[node.lineno - 1 : getattr(node, "end_lineno", node.lineno)]
		)
		parents: dict[ast.AST, ast.AST] = {}
		for parent in ast.walk(tree):
			for child in ast.iter_child_nodes(parent):
				parents[child] = parent
		chunks = []
		for node in ast.walk(tree):
			if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
				continue
			parent = parents.get(node)
			while parent is not None and not isinstance(parent, ast.ClassDef):
				parent = parents.get(parent)
			parent_class = parent.name if isinstance(parent, ast.ClassDef) else None
			symbol_type = "class" if isinstance(node, ast.ClassDef) else "function"
			self._append_symbol_chunk(
				chunks, repo_id, path, node.name, symbol_type, parent_class,
				node.lineno, getattr(node, "end_lineno", node.lineno), imports, lines,
				commit_sha, content_hash, "python",
			)
		return chunks

	def _tree_sitter_chunks(self, repo_id: str, path: str, content: str, commit_sha: str,
							language: str, content_hash: str | None) -> list[Chunk]:
		try:
			from tree_sitter_language_pack import get_parser
			tree = get_parser(language).parse(content.encode("utf-8"))
		except (ImportError, LookupError, ValueError):
			return []
		source = content.encode("utf-8")
		lines = content.splitlines()
		imports = "\n".join(line for line in lines if re.match(r"\s*(import|from|use|package)\s", line))
		chunks = []

		def visit(node, parent_class: str | None = None) -> None:
			symbol_type = _SYMBOL_TYPES.get(node.type)
			name_node = node.child_by_field_name("name")
			name = (source[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
					if name_node else None)
			next_parent = name if symbol_type == "class" and name else parent_class
			if symbol_type and name:
				self._append_symbol_chunk(
					chunks, repo_id, path, name, symbol_type, parent_class,
					node.start_point.row + 1, node.end_point.row + 1, imports, lines,
					commit_sha, content_hash, language,
				)
			for child in node.children:
				visit(child, next_parent)

		visit(tree.root_node)
		return chunks

	def _append_symbol_chunk(self, output: list[Chunk], repo_id: str, path: str,
							 symbol_name: str, symbol_type: str, parent_class: str | None,
							 start_line: int, end_line: int, imports: str, lines: list[str],
							 commit_sha: str, content_hash: str | None, language: str) -> None:
		source = "\n".join(lines[start_line - 1:end_line]).strip()
		if not source:
			return
		summary = self._summary(source).strip() if self._summary else ""
		text = f"Summary: {summary}\n\n{source}" if summary else source
		symbol = f"{parent_class}.{symbol_name}" if parent_class else symbol_name
		output.append(make_chunk(repo_id, path, symbol, commit_sha, text, {
			"chunk_type": "code", "language": language, "symbol_name": symbol_name,
			"symbol_type": symbol_type, "parent_class": parent_class,
			"start_line": start_line, "end_line": end_line, "imports_header": imports,
			"content_hash": content_hash or hashlib.sha256("\n".join(lines).encode()).hexdigest(),
		}))

	def _fallback(self, repo_id: str, path: str, content: str, commit_sha: str,
				  content_hash: str | None, language: str) -> list[Chunk]:
		tokens = list(re.finditer(r"\S+", content))
		if not tokens:
			return []
		step = self._window_tokens - self._overlap_tokens
		chunks = []
		for start in range(0, len(tokens), step):
			end = min(start + self._window_tokens, len(tokens))
			begin_offset, end_offset = tokens[start].start(), tokens[end - 1].end()
			start_line = content.count("\n", 0, begin_offset) + 1
			end_line = content.count("\n", 0, end_offset) + 1
			symbol = f"window:{start_line}-{end_line}"
			chunks.append(make_chunk(repo_id, path, symbol, commit_sha,
				content[begin_offset:end_offset], {
					"chunk_type": "code", "language": language, "symbol_name": symbol,
					"symbol_type": "window", "start_line": start_line,
					"end_line": end_line, "imports_header": "",
					"content_hash": content_hash or hashlib.sha256(content.encode()).hexdigest(),
				}))
			if end == len(tokens):
				break
		return chunks
