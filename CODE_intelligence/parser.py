from __future__ import annotations

import ast
import dataclasses
import pathlib
import re

LANGUAGE_BY_SUFFIX = {
    ".go": "go",
    ".java": "java",
    ".js": "javascript",
    ".jsx": "javascript",
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
}
HTTP_METHODS = {"delete", "get", "patch", "post", "put"}
_CALL_PATTERN = re.compile(r"\b([A-Za-z_$][\w$]*)\s*\(")
_ROUTE_PATTERN = re.compile(
    r"\.(get|post|put|delete|patch)\s*\(\s*['\"]([^'\"]+)['\"]",
    re.IGNORECASE,
)
_CONTROL_CALLS = {"if", "for", "while", "switch", "catch", "return", "new"}


@dataclasses.dataclass(frozen=True)
class CodeSymbol:
    name: str
    kind: str
    source: str
    start_line: int
    end_line: int
    signature: str
    text: str
    parent: str = ""
    calls: tuple[str, ...] = ()

    @property
    def qualified_name(self) -> str:
        return f"{self.parent}.{self.name}" if self.parent else self.name


@dataclasses.dataclass(frozen=True)
class ApiRoute:
    method: str
    path: str
    handler: str
    source: str
    line: int


@dataclasses.dataclass(frozen=True)
class FileAnalysis:
    source: str
    language: str
    parser_backend: str
    symbols: tuple[CodeSymbol, ...]
    imports: tuple[str, ...]
    routes: tuple[ApiRoute, ...]


def detect_language(source: str | pathlib.Path) -> str:
    return LANGUAGE_BY_SUFFIX.get(pathlib.Path(source).suffix.lower(), "unknown")


def parse_source(source: str, text: str, language: str | None = None) -> FileAnalysis:
    resolved_language = language or detect_language(source)
    if resolved_language == "python":
        return _parse_python(source, text)
    if resolved_language in {"javascript", "typescript", "java", "go"}:
        return _parse_tree_sitter(source, text, resolved_language)
    return FileAnalysis(source, resolved_language, "none", (), (), ())


def _parse_python(source: str, text: str) -> FileAnalysis:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return FileAnalysis(source, "python", "python-ast", (), (), ())

    symbols: list[CodeSymbol] = []
    imports: list[str] = []
    routes: list[ApiRoute] = []

    def visit(
        node: ast.AST,
        scope: tuple[str, ...] = (),
        inside_class: bool = False,
    ) -> None:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imports.append(ast.unparse(node))

        if isinstance(node, ast.ClassDef):
            text_value = ast.get_source_segment(text, node) or node.name
            symbols.append(CodeSymbol(
                name=node.name,
                kind="class",
                source=source,
                start_line=node.lineno,
                end_line=node.end_lineno or node.lineno,
                signature=f"class {node.name}",
                text=text_value,
                parent=".".join(scope),
            ))
            next_scope = (*scope, node.name)
            next_inside_class = True
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            kind = "method" if inside_class else "function"
            text_value = ast.get_source_segment(text, node) or node.name
            signature = text_value.splitlines()[0].strip()
            symbols.append(CodeSymbol(
                name=node.name,
                kind=kind,
                source=source,
                start_line=node.lineno,
                end_line=node.end_lineno or node.lineno,
                signature=signature,
                text=text_value,
                parent=".".join(scope),
                calls=_python_calls(node),
            ))
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call):
                    continue
                method = _attribute_name(decorator.func).lower()
                if method not in HTTP_METHODS or not decorator.args:
                    continue
                route_path = decorator.args[0]
                if isinstance(route_path, ast.Constant) and isinstance(route_path.value, str):
                    routes.append(ApiRoute(
                        method.upper(), route_path.value, node.name, source, decorator.lineno
                    ))
            next_scope = (*scope, node.name)
            next_inside_class = inside_class
        else:
            next_scope = scope
            next_inside_class = inside_class

        for child in ast.iter_child_nodes(node):
            visit(child, next_scope, next_inside_class)

    visit(tree)
    return FileAnalysis(
        source,
        "python",
        "python-ast",
        tuple(symbols),
        tuple(dict.fromkeys(imports)),
        tuple(routes),
    )


def _python_calls(node: ast.AST) -> tuple[str, ...]:
    calls = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            name = _attribute_name(child.func)
            if name:
                calls.add(name)
    return tuple(sorted(calls))


def _attribute_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _parse_tree_sitter(source: str, text: str, language: str) -> FileAnalysis:
    try:
        from tree_sitter_language_pack import get_parser
    except ImportError as exc:
        raise RuntimeError(
            "Install requirements-rag.txt to parse JavaScript, TypeScript, Java, and Go"
        ) from exc

    parser = get_parser(language)
    encoded = text.encode("utf-8")
    tree = parser.parse(encoded)
    symbol_types = {
        "javascript": {
            "function_declaration": "function",
            "generator_function_declaration": "function",
            "class_declaration": "class",
            "method_definition": "method",
        },
        "typescript": {
            "function_declaration": "function",
            "generator_function_declaration": "function",
            "class_declaration": "class",
            "method_definition": "method",
            "interface_declaration": "interface",
            "type_alias_declaration": "type",
        },
        "java": {
            "class_declaration": "class",
            "interface_declaration": "interface",
            "method_declaration": "method",
            "constructor_declaration": "method",
        },
        "go": {
            "function_declaration": "function",
            "method_declaration": "method",
            "type_spec": "type",
        },
    }[language]
    import_types = {
        "import_statement", "import_declaration", "export_statement",
    }
    symbols: list[CodeSymbol] = []
    imports: list[str] = []
    node_stack = [(tree.root_node, "")]
    while node_stack:
        node, parent = node_stack.pop()
        raw = encoded[node.start_byte : node.end_byte].decode("utf-8", errors="replace")
        if node.type in import_types:
            imports.append(raw.strip())
        kind = symbol_types.get(node.type)
        if kind:
            name_node = node.child_by_field_name("name")
            name = (
                encoded[name_node.start_byte : name_node.end_byte].decode("utf-8", errors="replace")
                if name_node is not None
                else _fallback_symbol_name(raw)
            )
            if name:
                symbols.append(CodeSymbol(
                    name=name,
                    kind=kind,
                    source=source,
                    start_line=node.start_point.row + 1,
                    end_line=node.end_point.row + 1,
                    signature=raw.splitlines()[0].strip(),
                    text=raw,
                    parent=parent,
                    calls=tuple(sorted(set(_CALL_PATTERN.findall(raw)) - _CONTROL_CALLS)),
                ))
                if kind in {"class", "interface", "type"}:
                    parent = f"{parent}.{name}" if parent else name
        node_stack.extend((child, parent) for child in reversed(node.children))

    routes = tuple(
        ApiRoute(method.upper(), path, "", source, text[: match.start()].count("\n") + 1)
        for match in _ROUTE_PATTERN.finditer(text)
        for method, path in [match.groups()]
    )
    return FileAnalysis(
        source,
        language,
        "tree-sitter",
        tuple(symbols),
        tuple(dict.fromkeys(imports)),
        routes,
    )


def _fallback_symbol_name(text: str) -> str:
    match = re.search(r"(?:function|class|interface|type|func|void)\s+([A-Za-z_$][\w$]*)", text)
    return match.group(1) if match else ""


__all__ = ["ApiRoute", "CodeSymbol", "FileAnalysis", "detect_language", "parse_source"]