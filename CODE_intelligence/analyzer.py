from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from CODE_intelligence.parser import CodeSymbol, FileAnalysis, parse_source

if TYPE_CHECKING:
    from Agents.RAG.loading import SourceDocument


@dataclass(frozen=True)
class CodeIntelligence:
    analyses: tuple[FileAnalysis, ...]
    function_map: dict[str, dict]
    class_map: dict[str, dict]
    dependency_map: dict[str, list[str]]
    call_graph: dict[str, list[str]]
    route_map: dict[str, dict]
    config_map: dict[str, dict]

    def to_dict(self) -> dict:
        return {
            "function_map": self.function_map,
            "class_map": self.class_map,
            "dependency_map": self.dependency_map,
            "call_graph": self.call_graph,
            "route_map": self.route_map,
            "config_map": self.config_map,
        }


def analyze_repository(documents: list[SourceDocument]) -> CodeIntelligence:
    analyses = tuple(
        parse_source(document.source, document.text)
        for document in documents
        if Path(document.source).suffix.lower() in {".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go"}
    )
    symbols = [symbol for analysis in analyses for symbol in analysis.symbols]
    function_map = {
        f"{symbol.source}:{symbol.qualified_name}": _symbol_record(symbol)
        for symbol in symbols
        if symbol.kind in {"function", "method"}
    }
    class_map = {
        f"{symbol.source}:{symbol.qualified_name}": _symbol_record(symbol)
        for symbol in symbols
        if symbol.kind in {"class", "interface", "type"}
    }
    dependency_map = {
        analysis.source: list(analysis.imports)
        for analysis in analyses
        if analysis.imports
    }
    call_graph = {
        f"{symbol.source}:{symbol.qualified_name}": list(symbol.calls)
        for symbol in symbols
        if symbol.calls
    }
    route_map = {
        f"{route.method} {route.path}": {
            "method": route.method,
            "path": route.path,
            "handler": route.handler,
            "source": route.source,
            "line": route.line,
        }
        for analysis in analyses
        for route in analysis.routes
    }
    config_map = {
        document.source: _config_summary(document)
        for document in documents
        if Path(document.source).suffix.lower() in {".json", ".toml", ".yaml", ".yml"}
    }
    return CodeIntelligence(
        analyses,
        function_map,
        class_map,
        dependency_map,
        call_graph,
        route_map,
        config_map,
    )


def _symbol_record(symbol: CodeSymbol) -> dict:
    return {
        "name": symbol.name,
        "kind": symbol.kind,
        "source": symbol.source,
        "start_line": symbol.start_line,
        "end_line": symbol.end_line,
        "signature": symbol.signature,
        "calls": list(symbol.calls),
    }


def _config_summary(document: SourceDocument) -> dict:
    suffix = Path(document.source).suffix.lower()
    try:
        if suffix == ".json":
            value: Any = json.loads(document.text)
        elif suffix in {".yaml", ".yml"}:
            import yaml

            value = yaml.safe_load(document.text)
        elif suffix == ".toml":
            try:
                import tomllib
            except ImportError:
                import tomli as tomllib

            value = tomllib.loads(document.text)
        else:
            value = None
    except Exception:
        value = None
    keys = sorted(map(str, value)) if isinstance(value, dict) else []
    return {
        "format": suffix.lstrip("."),
        "top_level_keys": keys[:100],
        "summary": f"Configuration file with {len(keys)} top-level keys.",
    }


__all__ = ["CodeIntelligence", "analyze_repository"]