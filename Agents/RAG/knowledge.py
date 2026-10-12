from __future__ import annotations

import hashlib
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from Agents.Graph.knowledge_graph import RepositoryKnowledgeGraph
from CODE_intelligence.analyzer import CodeIntelligence, analyze_repository
from Agents.RAG.loading import (
    IGNORED_DIRECTORIES,
    SUPPORTED_SUFFIXES,
    SourceDocument,
    load_documents,
)
from CODE_intelligence.parser import FileAnalysis
from schemas.repo import RepositoryKnowledge


@dataclass(frozen=True)
class RepositoryContext:
    knowledge: RepositoryKnowledge
    documents: tuple[SourceDocument, ...]
    analyses: tuple[FileAnalysis, ...]
    graph: RepositoryKnowledgeGraph
    intelligence: CodeIntelligence


class RepositoryCache:
    """Small in-process cache invalidated by path, size, and modification time."""

    def __init__(self):
        self._entries: dict[str, tuple[str, tuple[SourceDocument, ...]]] = {}
        self._lock = threading.RLock()

    def load(
        self,
        root: str | Path,
        *,
        max_file_size_bytes: int,
    ) -> list[SourceDocument]:
        repository = Path(root).expanduser().resolve()
        files = sorted(
            path
            for path in repository.rglob("*")
            if path.is_file()
            and path.suffix.lower() in SUPPORTED_SUFFIXES
            and not any(part.lower() in IGNORED_DIRECTORIES for part in path.parts)
        )
        fingerprint = hashlib.sha256()
        for file_path in files:
            try:
                stat = file_path.stat()
            except OSError:
                continue
            fingerprint.update(
                f"{file_path.relative_to(repository).as_posix()}:{stat.st_size}:{stat.st_mtime_ns}".encode()
            )
        signature = fingerprint.hexdigest()
        key = str(repository)
        with self._lock:
            entry = self._entries.get(key)
            if entry and entry[0] == signature:
                return list(entry[1])
        documents = tuple(load_documents(
            repository,
            root=repository,
            max_file_size_bytes=max_file_size_bytes,
        ))
        with self._lock:
            self._entries[key] = (signature, documents)
        return list(documents)

    def invalidate(self, root: str | Path) -> None:
        with self._lock:
            self._entries.pop(str(Path(root).expanduser().resolve()), None)


_DEFAULT_CACHE = RepositoryCache()


def build_repository_knowledge(
    repository_name: str,
    documents: list[SourceDocument],
    *,
    documentation: Any | None = None,
    graph_namespace: str | None = None,
) -> RepositoryContext:
    intelligence = analyze_repository(documents)
    analyses = intelligence.analyses
    graph = RepositoryKnowledgeGraph(graph_namespace or repository_name)
    graph.add_analyses(list(analyses))
    graph.add_documents(documents)
    folders = _folder_summaries(documents)
    for folder, details in folders.items():
        directory = graph.add_node(
            folder,
            "directory",
            folder,
            details["purpose"],
            {"files": details["files"]},
        )
        for source in details["files"]:
            file_node = graph.add_node(source, "file", source)
            graph.add_edge(directory, file_node, "contains", source)

    languages = sorted({
        analysis.language for analysis in analyses if analysis.language != "unknown"
    })
    symbols = [symbol for analysis in analyses for symbol in analysis.symbols]
    file_metadata = {
        document.source: {
            "language": next(
                (analysis.language for analysis in analyses if analysis.source == document.source),
                _language_for_document(document.source),
            ),
            "symbols": [symbol.qualified_name for symbol in symbols if symbol.source == document.source],
            "imports": list(next(
                (analysis.imports for analysis in analyses if analysis.source == document.source),
                (),
            )),
            "summary": _first_sentence(document.text),
            "configuration": intelligence.config_map.get(document.source),
        }
        for document in documents
    }
    routes = list(intelligence.route_map.values())
    summary = _documentation_value(documentation, "repository_summary") or _build_summary(
        repository_name, documents, languages, symbols, routes
    )
    architecture = _documentation_value(documentation, "architecture_overview") or (
        f"{repository_name} contains {len(documents)} indexed files, "
        f"{len(symbols)} parsed symbols, and {len(routes)} detected API routes."
    )
    knowledge = RepositoryKnowledge(
        repository_name=repository_name,
        repo_summary=summary,
        tech_stack=_documentation_value(documentation, "tech_stack") or languages,
        architecture=architecture,
        folders=_path_mapping(_documentation_value(documentation, "folders")) or folders,
        files=_path_mapping(_documentation_value(documentation, "files")) or file_metadata,
        classes=intelligence.class_map,
        functions=intelligence.function_map,
        dependencies=intelligence.dependency_map,
        execution_flows={
            "api_routes": routes,
            "call_graph": intelligence.call_graph,
            "documented_flows": _named_mapping(
                _documentation_value(documentation, "execution_flows")
            ),
        },
        embeddings_id=None,
        graph_id=repository_name,
    )
    return RepositoryContext(
        knowledge,
        tuple(documents),
        analyses,
        graph,
        intelligence,
    )


def load_repository_context(
    repository_name: str,
    root: str | Path,
    *,
    file_tree: list[str] | None = None,
    max_file_size_bytes: int = 512 * 1024,
    documentation: Any | None = None,
    cache: RepositoryCache | None = None,
    graph_namespace: str | None = None,
) -> RepositoryContext:
    if file_tree is not None:
        repository = Path(root).expanduser().resolve()
        documents = load_documents(
            file_tree,
            root=repository,
            max_file_size_bytes=max_file_size_bytes,
        )
    else:
        documents = (cache or _DEFAULT_CACHE).load(
            root,
            max_file_size_bytes=max_file_size_bytes,
        )
    return build_repository_knowledge(
        repository_name,
        documents,
        documentation=documentation,
        graph_namespace=graph_namespace,
    )


def _documentation_value(documentation: Any | None, key: str):
    if documentation is None:
        return None
    if isinstance(documentation, dict):
        return documentation.get(key)
    return getattr(documentation, key, None)


def _model_mapping(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return {}


def _path_mapping(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if not isinstance(value, list):
        return {}
    mapped = {}
    for item in value:
        item_data = _model_mapping(item)
        path = item_data.get("path")
        if path:
            mapped[path] = item_data
    return mapped


def _named_mapping(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if not isinstance(value, list):
        return {}
    mapped = {}
    for index, item in enumerate(value):
        item_data = _model_mapping(item)
        name = item_data.get("name", f"flow-{index + 1}")
        mapped[name] = item_data
    return mapped


def _first_sentence(text: str, max_chars: int = 240) -> str:
    first_line = next((line.strip(" #\t") for line in text.splitlines() if line.strip()), "")
    sentence_end = first_line.find(". ")
    if sentence_end >= 0:
        first_line = first_line[: sentence_end + 1]
    return first_line[:max_chars]


def _build_summary(repository_name, documents, languages, symbols, routes) -> str:
    names = ", ".join(languages) or "unclassified languages"
    top_symbols = ", ".join(symbol.name for symbol in symbols[:8]) or "no parsed symbols"
    route_summary = (
        f" It exposes {len(routes)} detected API routes."
        if routes else " No API routes were detected in the parsed files."
    )
    file_summaries = "; ".join(
        f"{document.source}: {_first_sentence(document.text)}"
        for document in documents[:5]
        if _first_sentence(document.text)
    )
    return (
        f"{repository_name} contains {len(documents)} supported source and documentation files. "
        f"Detected languages include {names}. Parsed symbols include {top_symbols}.{route_summary} "
        f"File summaries: {file_summaries or 'No non-empty summaries were available.'}"
    )


def _folder_summaries(documents: list[SourceDocument]) -> dict:
    folders: dict[str, list[str]] = {}
    for document in documents:
        parent = str(Path(document.source).parent).replace("\\", "/")
        folder = "." if parent in {"", "."} else parent
        folders.setdefault(folder, []).append(document.source)
    return {
        folder: {
            "files": paths,
            "purpose": f"Contains {len(paths)} indexed files.",
        }
        for folder, paths in folders.items()
    }


def _language_for_document(source: str) -> str:
    from CODE_intelligence.parser import detect_language

    return detect_language(source)


__all__ = [
    "RepositoryCache",
    "RepositoryContext",
    "build_repository_knowledge",
    "load_repository_context",
]