import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from CODE_intelligence.parser import parse_source
from Agents.RAG.chunking import ChunkingEngine
from Agents.RAG.knowledge import build_repository_knowledge
from Agents.RAG.generator.citations import SourceCiter
from Agents.RAG.generator.compression import ContextCompressor
from Agents.RAG.indexer import delete_repository_rag_documents
from Agents.RAG.openforge_ai import ask_codebase_question
from Agents.RAG.indexer import index_repository_files
from Agents.RAG.loading import SourceDocument, chunk_documents, load_documents
from Agents.RAG.retriever.retrieval import RetrievedChunk, SupabaseRetriever
from Agents.RAG.router import route_query


class FakeEmbedder:
    def embed(self, texts):
        for _ in texts:
            yield [0.1, 0.2, 0.3]


class FakeQuery:
    def __init__(self, data=None):
        self.data = data or []
        self.rows = None
        self.filters = []

    def upsert(self, rows, **kwargs):
        self.rows = rows
        return self

    def delete(self):
        self.deleted = True
        return self

    def eq(self, field, value):
        self.filters.append((field, value))
        return self

    def execute(self):
        return SimpleNamespace(data=self.data)


class FakeClient:
    def __init__(self, matches=None):
        self.matches = matches or []
        self.query = FakeQuery(self.matches)
        self.tables = {}
        self.rpc_call = None
        self.rpc_calls = []

    def table(self, name):
        if name not in self.tables:
            self.tables[name] = FakeQuery()
        return self.tables[name]

    def rpc(self, name, arguments):
        self.rpc_call = (name, arguments)
        self.rpc_calls.append((name, arguments))
        return self.query


class RagTests(unittest.IsolatedAsyncioTestCase):
    def test_router_and_source_citer_select_and_normalize(self):
        self.assertEqual(route_query("Explain the architecture and dependencies").intent, "architecture")
        self.assertEqual(route_query("Where does the request handler live?").intent, "code")
        cited = SourceCiter().cite(
            "The app starts here 【src/main.py】.",
            [RetrievedChunk("main", "src/main.py")],
        )
        self.assertEqual(cited, "The app starts here [src/main.py].")

    def test_documentation_agent_output_maps_into_repository_knowledge(self):
        document = SourceDocument("README.md", "A small test repository.")
        context = build_repository_knowledge("owner/repo", [document], documentation={
            "repository_summary": "Generated summary",
            "architecture_overview": "A generated architecture description.",
            "tech_stack": ["Python"],
            "folders": [{"path": "src", "purpose": "Application code"}],
            "files": [{"path": "src/app.py", "summary": "Application entry point"}],
            "execution_flows": [{"name": "Startup", "flow_steps": ["load", "run"]}],
        })
        self.assertEqual(context.knowledge.repo_summary, "Generated summary")
        self.assertIn("src", context.knowledge.folders)
        self.assertIn("src/app.py", context.knowledge.files)
        self.assertIn("Startup", context.knowledge.execution_flows["documented_flows"])

    def test_graph_ids_are_scoped_and_cleanup_covers_all_rag_stores(self):
        document = SourceDocument("app.py", "def start():\n    return True")
        first = build_repository_knowledge(
            "owner/repo", [document], graph_namespace="user-a:owner/repo"
        )
        second = build_repository_knowledge(
            "owner/repo", [document], graph_namespace="user-b:owner/repo"
        )
        self.assertTrue(set(first.graph.nodes).isdisjoint(second.graph.nodes))

        client = FakeClient()
        delete_repository_rag_documents("user-a", "owner/repo", client=client)
        self.assertEqual(
            set(client.tables),
            {"rag_documents", "rag_graph_edges", "rag_graph_nodes", "rag_repository_knowledge"},
        )
        self.assertTrue(all(query.deleted for query in client.tables.values()))

    def test_context_compression_keeps_distinct_sources_and_removes_duplicates(self):
        chunks = [
            RetrievedChunk("same evidence", "one.py"),
            RetrievedChunk("same evidence", "two.py"),
            RetrievedChunk("same evidence", "one.py"),
        ]
        compressed = ContextCompressor().compress(chunks)
        self.assertEqual([chunk.source for chunk in compressed], ["one.py", "two.py"])

    def test_python_parser_extracts_symbols_imports_calls_and_routes(self):
        analysis = parse_source("app.py", """import os

class App:
    def health(self):
        return os.getcwd()

@app.get('/health')
def health_route():
    return App().health()
""")

        symbols = {symbol.name: symbol for symbol in analysis.symbols}
        self.assertIn("import os", analysis.imports)
        self.assertEqual(symbols["App"].kind, "class")
        self.assertEqual(symbols["health"].kind, "method")
        self.assertIn("getcwd", symbols["health"].calls)
        self.assertEqual(analysis.routes[0].path, "/health")

    def test_tree_sitter_parses_javascript_typescript_java_and_go(self):
        samples = {
            "javascript": ("app.js", "import { helper } from './lib'; export function start() { helper(); }", "start"),
            "typescript": ("app.ts", "interface User { id: string; } export function loadUser(): User { return { id: '1' }; }", "User"),
            "java": ("App.java", "package app; class App { void run() {} }", "App"),
            "go": ("app.go", 'package app\nfunc Start() {}\ntype App struct {}', "Start"),
        }
        for language, (path, source, expected_symbol) in samples.items():
            with self.subTest(language=language):
                analysis = parse_source(path, source, language)
                self.assertEqual(analysis.parser_backend, "tree-sitter")
                self.assertIn(expected_symbol, {symbol.name for symbol in analysis.symbols})

    def test_knowledge_graph_and_three_chunk_families_are_built(self):
        document = SourceDocument(
            "src/app.py",
            "import json\n\nclass App:\n    def run(self):\n        return json.dumps({})\n",
        )
        config = SourceDocument("config/settings.json", '{"debug": true}')
        context = build_repository_knowledge("owner/repo", [document, config])
        chunks = ChunkingEngine(chunk_size=30, overlap=4).build(context)

        self.assertIn("python", context.knowledge.tech_stack)
        file_node = next(
            node for node in context.graph.nodes.values()
            if node.kind == "file" and node.source == "src/app.py"
        )
        self.assertEqual(file_node.metadata["language"], "python")
        self.assertIn("src/app.py:App.run", context.intelligence.function_map)
        self.assertIn("src/app.py", context.intelligence.dependency_map)
        self.assertIn("src/app.py:App.run", context.intelligence.call_graph)
        self.assertEqual(
            context.intelligence.config_map["config/settings.json"]["top_level_keys"],
            ["debug"],
        )
        self.assertTrue(any(edge.relation == "defines" for edge in context.graph.edges.values()))
        self.assertTrue(any(edge.relation == "calls" for edge in context.graph.edges.values()))
        self.assertEqual(
            {"ast", "semantic", "hierarchical"},
            {chunk.chunk_kind for chunk in chunks},
        )
        self.assertTrue(all(chunk.source for chunk in chunks))

    def test_loader_skips_generated_directories_and_chunks_with_overlap(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "src").mkdir()
            (root / "src" / "main.py").write_text("one two three four five", encoding="utf-8")
            (root / "node_modules").mkdir()
            (root / "node_modules" / "ignored.py").write_text("ignored", encoding="utf-8")
            (root / "package-lock.json").write_text("{}", encoding="utf-8")
            (root / "bundle.min.js").write_text("generated", encoding="utf-8")
            (root / "binary.py").write_bytes(b"\x00\x01\x02")

            documents = load_documents(root, root=root)

        self.assertEqual([document.source for document in documents], ["src/main.py"])
        chunks = chunk_documents(documents, chunk_size=3, overlap=1)
        self.assertEqual([chunk.text for chunk in chunks], ["one two three", "three four five"])
        self.assertEqual([chunk.chunk_id for chunk in chunks], [0, 1])

    def test_indexer_upserts_scoped_rows(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "main.py").write_text("def answer(): return 42", encoding="utf-8")
            client = FakeClient()

            count = index_repository_files(
                "user-1",
                "owner/repo",
                root,
                client=client,
                embedder=FakeEmbedder(),
            )

        indexed_rows = client.tables["rag_documents"].rows
        self.assertGreater(count, 1)
        self.assertTrue(all(row["user_id"] == "user-1" for row in indexed_rows))
        self.assertTrue(all(row["repository_id"] == "owner/repo" for row in indexed_rows))
        self.assertTrue(any(row["source"] == "main.py" for row in indexed_rows))
        self.assertTrue(any(row["language"] == "python" for row in indexed_rows))
        self.assertTrue(any(row["chunk_type"] == "code" for row in indexed_rows))
        self.assertEqual(
            {"semantic", "ast", "hierarchical"},
            {row["chunk_kind"] for row in indexed_rows},
        )
        self.assertIn("rag_repository_knowledge", client.tables)
        self.assertIn("rag_graph_nodes", client.tables)
        self.assertIn("rag_graph_edges", client.tables)

    def test_retriever_scopes_rpc_and_qa_returns_source_metadata(self):
        client = FakeClient([{
            "content": "The app starts in main.py.",
            "source": "main.py",
            "language": "python",
            "similarity": 0.9,
        }])
        retriever = SupabaseRetriever(
            "user-1",
            "owner/repo",
            client=client,
            embedder=FakeEmbedder(),
        )

        class FakeLLM:
            async def ainvoke(self, messages):
                self.messages = messages
                return SimpleNamespace(content="The app starts in [main.py].")

        llm = FakeLLM()
        result = asyncio.run(ask_codebase_question(
            "Where does the app start?",
            "user-1",
            "owner/repo",
            llm=llm,
            retriever=retriever,
        ))

        dense_call = next(call for call in client.rpc_calls if call[0] == "match_rag_documents")
        self.assertEqual(dense_call[1]["match_user_id"], "user-1")
        self.assertEqual(dense_call[1]["match_repository_id"], "owner/repo")
        self.assertIn("search_rag_documents", [call[0] for call in client.rpc_calls])
        self.assertIn("search_rag_graph_nodes", [call[0] for call in client.rpc_calls])
        self.assertEqual(result["chunk_count"], 1)
        self.assertEqual(result["sources"][0]["file"], "main.py")
        self.assertIn("The app starts", result["answer"])


if __name__ == "__main__":
    unittest.main()