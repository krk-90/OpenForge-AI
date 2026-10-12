from __future__ import annotations

import json
from dataclasses import dataclass, field
from hashlib import sha256

from CODE_intelligence.parser import FileAnalysis


@dataclass(frozen=True)
class GraphNode:
    id: str
    name: str
    kind: str
    source: str
    summary: str
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class GraphEdge:
    id: str
    source_node: str
    target_node: str
    relation: str
    source: str
    metadata: dict = field(default_factory=dict)


class RepositoryKnowledgeGraph:
    def __init__(self, namespace: str = ""):
        self.namespace = namespace
        self.nodes: dict[str, GraphNode] = {}
        self.edges: dict[str, GraphEdge] = {}

    def _stable_id(self, *parts: str) -> str:
        return sha256(":".join((self.namespace, *parts)).encode("utf-8")).hexdigest()

    def add_node(
        self,
        name: str,
        kind: str,
        source: str,
        summary: str = "",
        metadata: dict | None = None,
    ) -> GraphNode:
        node_id = self._stable_id("node", kind, source, name)
        existing = self.nodes.get(node_id)
        merged_metadata = dict(existing.metadata) if existing else {}
        merged_metadata.update(metadata or {})
        node = GraphNode(
            node_id,
            name,
            kind,
            source,
            (existing.summary if existing and existing.summary else summary),
            merged_metadata,
        )
        self.nodes[node_id] = node
        return node

    def add_edge(
        self,
        source_node: GraphNode,
        target_node: GraphNode,
        relation: str,
        source: str,
        metadata: dict | None = None,
    ) -> GraphEdge:
        edge_id = self._stable_id(
            "edge", source_node.id, target_node.id, relation, source
        )
        edge = GraphEdge(
            edge_id,
            source_node.id,
            target_node.id,
            relation,
            source,
            metadata or {},
        )
        self.edges[edge_id] = edge
        return edge

    def add_analyses(self, analyses: list[FileAnalysis]) -> None:
        files: dict[str, GraphNode] = {}
        symbols_by_name: dict[str, list[GraphNode]] = {}
        pending_calls: list[tuple[GraphNode, str, str]] = []

        for analysis in analyses:
            file_node = self.add_node(
                analysis.source,
                "file",
                analysis.source,
                f"{analysis.language} source file",
                {"language": analysis.language},
            )
            files[analysis.source] = file_node
            for symbol in analysis.symbols:
                symbol_node = self.add_node(
                    symbol.qualified_name,
                    symbol.kind,
                    symbol.source,
                    symbol.signature,
                    {
                        "start_line": symbol.start_line,
                        "end_line": symbol.end_line,
                        "calls": list(symbol.calls),
                    },
                )
                symbols_by_name.setdefault(symbol.name, []).append(symbol_node)
                self.add_edge(file_node, symbol_node, "defines", analysis.source)
                pending_calls.extend(
                    (symbol_node, call_name, analysis.source)
                    for call_name in symbol.calls
                )

            for import_name in analysis.imports:
                dependency_name = _dependency_name(import_name)
                if not dependency_name:
                    continue
                dependency = self.add_node(
                    dependency_name,
                    "dependency",
                    analysis.source,
                    f"Imported by {analysis.source}",
                )
                self.add_edge(file_node, dependency, "imports", analysis.source)

            for route in analysis.routes:
                route_node = self.add_node(
                    f"{route.method} {route.path}",
                    "route",
                    route.source,
                    f"API route handled by {route.handler or 'unknown handler'}",
                    {"method": route.method, "path": route.path, "line": route.line},
                )
                self.add_edge(file_node, route_node, "exposes", route.source)
                handlers = symbols_by_name.get(route.handler, [])
                for handler in handlers:
                    if handler.source == route.source:
                        self.add_edge(route_node, handler, "handled_by", route.source)

        for caller, call_name, source in pending_calls:
            targets = symbols_by_name.get(call_name, [])
            if not targets:
                targets = [self.add_node(
                    call_name,
                    "external_symbol",
                    source,
                    f"External or unresolved call to {call_name}",
                )]
            for target in targets:
                self.add_edge(caller, target, "calls", source)

    def add_documents(self, documents) -> None:
        for document in documents:
            summary = next(
                (line.strip(" #") for line in document.text.splitlines() if line.strip()),
                "",
            )
            node_id = self._stable_id("node", "file", document.source, document.source)
            existing = self.nodes.get(node_id)
            if existing:
                self.nodes[node_id] = GraphNode(
                    existing.id,
                    existing.name,
                    existing.kind,
                    existing.source,
                    existing.summary or summary,
                    existing.metadata,
                )
            else:
                self.add_node(document.source, "file", document.source, summary)

    def to_node_rows(self) -> list[dict]:
        return [
            {
                "id": node.id,
                "name": node.name,
                "kind": node.kind,
                "source": node.source,
                "summary": node.summary,
                "metadata": json.loads(json.dumps(node.metadata, default=str)),
            }
            for node in self.nodes.values()
        ]

    def to_edge_rows(self) -> list[dict]:
        return [
            {
                "id": edge.id,
                "source_node": edge.source_node,
                "target_node": edge.target_node,
                "relation": edge.relation,
                "source": edge.source,
                "metadata": json.loads(json.dumps(edge.metadata, default=str)),
            }
            for edge in self.edges.values()
        ]


def _dependency_name(import_value: str) -> str:
    value = import_value.strip()
    if value.startswith("from "):
        value = value[5:].split(" import ", 1)[0]
    elif " from " in value:
        value = value.rsplit(" from ", 1)[-1].strip("'\";")
    elif value.startswith("import "):
        value = value[7:].split(",", 1)[0].split(" as ", 1)[0]
    elif value.startswith("import "):
        value = value[7:].strip("'\";")
    return value.strip("'\"; ")


__all__ = ["GraphEdge", "GraphNode", "RepositoryKnowledgeGraph"]