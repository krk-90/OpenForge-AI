from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


SUPPORTED_SUFFIXES = {
    ".c", ".cc", ".cpp", ".cs", ".css", ".dart", ".go", ".h", ".html",
    ".java", ".js", ".jsx", ".json", ".kt", ".lua", ".md", ".php", ".py",
    ".rb", ".rs", ".rst", ".scala", ".scss", ".sh", ".sql", ".swift",
    ".toml", ".ts", ".tsx", ".txt", ".vue", ".xml", ".yaml", ".yml",
}
IGNORED_DIRECTORIES = {
    ".git", ".next", ".pytest_cache", ".venv", "__pycache__", "bin", "build",
    "coverage", "dist", "generated", "node_modules", "obj", "target", "vendor", "venv",
}
IGNORED_FILENAMES = {
    "bun.lock", "bun.lockb", "cargo.lock", "composer.lock", "gemfile.lock", "go.sum",
    "mix.lock", "npm-shrinkwrap.json", "package-lock.json", "pnpm-lock.yaml",
    "poetry.lock", "uv.lock", "yarn.lock",
}
MAX_FILE_SIZE_BYTES = 512 * 1024


@dataclass(frozen=True)
class SourceDocument:
    source: str
    text: str


@dataclass(frozen=True)
class DocumentChunk:
    text: str
    source: str
    chunk_id: int
    chunk_kind: str = "semantic"
    symbols: tuple[str, ...] = ()
    metadata: dict = field(default_factory=dict)


def _is_ignored(path: Path) -> bool:
    filename = path.name.lower()
    return (
        any(part.lower() in IGNORED_DIRECTORIES for part in path.parts)
        or filename in IGNORED_FILENAMES
        or filename.endswith((
            ".min.js", ".min.css", ".map", ".pb.go", "_generated.go",
            "_generated.py", "_pb2.py", "_pb2_grpc.py",
        ))
    )


def load_documents(
    paths: str | Path | Iterable[str | Path],
    *,
    root: str | Path | None = None,
    max_file_size_bytes: int = MAX_FILE_SIZE_BYTES,
) -> list[SourceDocument]:
    """Read supported text files, storing repository-relative source paths when possible."""
    items = [paths] if isinstance(paths, (str, Path)) else list(paths)
    resolved_root = Path(root).expanduser().resolve() if root is not None else None
    documents: list[SourceDocument] = []

    for item in items:
        item_path = Path(item).expanduser()
        candidate = item_path.resolve() if item_path.is_absolute() else (
            (resolved_root / item_path).resolve() if resolved_root else item_path.resolve()
        )
        if resolved_root is not None:
            try:
                candidate.relative_to(resolved_root)
            except ValueError:
                continue
        if not candidate.exists():
            continue

        candidates = [candidate] if candidate.is_file() else sorted(candidate.rglob("*"))
        for file_path in candidates:
            if (
                not file_path.is_file()
                or file_path.suffix.lower() not in SUPPORTED_SUFFIXES
                or _is_ignored(file_path)
            ):
                continue
            if resolved_root is not None:
                try:
                    file_path.resolve().relative_to(resolved_root)
                except ValueError:
                    continue
            try:
                if file_path.stat().st_size > max_file_size_bytes:
                    continue
                raw = file_path.read_bytes()
                if b"\x00" in raw[:8192]:
                    continue
                text = raw.decode("utf-8", errors="ignore").strip()
            except OSError:
                continue
            if not text:
                continue
            source = (
                file_path.resolve().relative_to(resolved_root).as_posix()
                if resolved_root is not None
                else str(file_path.resolve())
            )
            documents.append(SourceDocument(source, text))
    return documents


def chunk_documents(
    documents: Iterable[SourceDocument],
    chunk_size: int = 800,
    overlap: int = 120,
) -> list[DocumentChunk]:
    if chunk_size <= 0 or overlap < 0 or overlap >= chunk_size:
        raise ValueError("chunk_size must be positive and overlap must be smaller than chunk_size")

    chunks: list[DocumentChunk] = []
    step = chunk_size - overlap
    for document in documents:
        words = document.text.split()
        for chunk_id, start in enumerate(range(0, len(words), step)):
            text = " ".join(words[start : start + chunk_size]).strip()
            if text:
                chunks.append(DocumentChunk(
                    text,
                    document.source,
                    chunk_id,
                    chunk_kind="semantic",
                ))
            if start + chunk_size >= len(words):
                break
    return chunks


__all__ = ["DocumentChunk", "SourceDocument", "chunk_documents", "load_documents"]