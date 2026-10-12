import hashlib
import re

from RAG.chunking.chunk_metadata import make_chunk
from RAG.models import Chunk

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


class MarkdownChunker:
	def __init__(self, max_tokens: int = 800, overlap_tokens: int = 100) -> None:
		if max_tokens < 1 or not 0 <= overlap_tokens < max_tokens:
			raise ValueError("overlap_tokens must be non-negative and smaller than max_tokens")
		self._max_tokens = max_tokens
		self._overlap_tokens = overlap_tokens

	def chunk(self, repo_id: str, path: str, content: str, commit_sha: str,
			  content_hash: str | None = None, chunk_type: str = "documentation") -> list[Chunk]:
		lines = content.splitlines()
		headings: list[tuple[int, str]] = []
		sections: list[tuple[str, int, list[str]]] = []
		current_lines: list[str] = []
		section_start = 1
		for line_number, line in enumerate(lines, start=1):
			match = _HEADING.match(line)
			if match:
				if current_lines:
					sections.append((" / ".join(title for _, title in headings), section_start, current_lines))
				level = len(match.group(1))
				headings = [(depth, title) for depth, title in headings if depth < level]
				headings.append((level, match.group(2).strip()))
				current_lines = [line]
				section_start = line_number
			else:
				current_lines.append(line)
		if current_lines:
			sections.append((" / ".join(title for _, title in headings), section_start, current_lines))
		if not sections and content.strip():
			sections.append(("", 1, lines))
		chunks = []
		for heading_path, start_line, section_lines in sections:
			section_text = "\n".join(section_lines)
			tokens = list(re.finditer(r"\S+", section_text))
			if not tokens:
				continue
			step = self._max_tokens - self._overlap_tokens
			for offset in range(0, len(tokens), step):
				last = min(offset + self._max_tokens, len(tokens))
				text = section_text[tokens[offset].start():tokens[last - 1].end()]
				line_start = start_line + section_text.count("\n", 0, tokens[offset].start())
				line_end = start_line + section_text.count("\n", 0, tokens[last - 1].end())
				symbol = f"{heading_path or 'document'}:{offset}"
				chunks.append(make_chunk(repo_id, path, symbol, commit_sha, text, {
					"chunk_type": chunk_type, "heading_path": heading_path,
					"start_line": line_start, "end_line": line_end,
					"content_hash": content_hash or hashlib.sha256(content.encode()).hexdigest(),
				}))
				if last == len(tokens):
					break
		return chunks
