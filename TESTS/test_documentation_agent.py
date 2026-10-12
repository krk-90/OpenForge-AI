import argparse
import json
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pydantic import ValidationError

project_root = str(Path(__file__).resolve().parents[1])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from Agents.documentation_agent import DocumentationAgent
from MCP_server.server.github_git_server import get_openforge_tools
from schemas.repo import DocAgentRequest, RepositoryDocumentation


class FakeTool:
    def __init__(self, name):
        self.name = name
        self.args_schema = None
        self.paths = []

    async def ainvoke(self, arguments):
        if self.name == "get_tree":
            return {
                "tree": [
                    {"path": "README.md", "type": "blob"},
                    {"path": "src/main.py", "type": "blob"},
                ]
            }
        self.paths.append(arguments["path"])
        return "print('hello')"


class FakeLLM:
    def __init__(self, payload):
        self.payload = payload

    async def ainvoke(self, messages):
        return SimpleNamespace(content=json.dumps(self.payload))


class DocumentationAgentTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.payload = {
            "repository_name": "acme/demo",
            "repository_summary": "This repository provides a carefully structured example of a software project. " * 8,
            "architecture_overview": "A small service organized around a main module.",
            "tech_stack": ["Python"],
            "main_modules": ["src"],
            "folders": [{
                "path": "src",
                "purpose": "Application code",
                "responsibilities": ["Run the service"],
                "important_files": ["src/main.py"],
            }],
            "files": [{
                "path": "src/main.py",
                "purpose": "Entry point",
                "classes": [],
                "functions": ["main"],
                "dependencies": [],
                "summary": "Starts the service.",
            }],
            "execution_flows": [{
                "name": "Startup",
                "description": "Starts the application.",
                "flow_steps": ["Load config", "Run server"],
            }],
            "diagrams": [],
            "contributor_guide": {
                "difficulty": "beginner",
                "starting_points": ["src/main.py"],
                "suggested_issues": [],
            },
            "improvement_suggestions": [],
            "generated_word_count": 40,
        }
        self.tree_tool = FakeTool("get_tree")
        self.file_tool = FakeTool("get_file_contents")
        self.agent = DocumentationAgent(
            [self.tree_tool, self.file_tool],
            llm=FakeLLM(self.payload),
        )
        self.request = DocAgentRequest.model_validate({
            "repository": {"repo_url": "https://github.com/acme/demo"},
            "explanation_type": "repository",
            "output_mode": "json",
        })

    async def test_generates_valid_documentation_and_renders_output_modes(self):
        documentation = await self.agent.generate(self.request)

        self.assertIsInstance(documentation, RepositoryDocumentation)
        self.assertIn("src/main.py", self.file_tool.paths)
        with patch("Agents.documentation_agent.save_generated_documentation") as save_doc:
            with patch(
                "Agents.documentation_agent.get_generated_documentation",
                return_value={
                    "document": json.dumps(self.payload),
                    "output_format": "json",
                },
            ) as get_doc:
                result = await self.agent.run(self.request)
        self.assertEqual(json.loads(result)["repository_name"], "acme/demo")
        save_doc.assert_called_once()
        get_doc.assert_called_once_with("acme/demo")
        self.assertTrue(
            self.agent.format_documentation(documentation, "markdown").startswith("# acme/demo")
        )
        self.assertIn(
            "<h1>acme/demo</h1>",
            self.agent.format_documentation(documentation, "html"),
        )

    async def test_run_fails_when_supabase_does_not_return_document(self):
        with patch("Agents.documentation_agent.save_generated_documentation"):
            with patch(
                "Agents.documentation_agent.get_generated_documentation",
                return_value=None,
            ):
                with self.assertRaisesRegex(RuntimeError, "was not returned by Supabase"):
                    await self.agent.run(self.request)

    def test_request_and_document_constraints_are_enforced(self):
        with self.assertRaises(ValidationError):
            DocAgentRequest.model_validate({
                "repository": {"repo_url": "https://github.com/acme/demo"},
                "explanation_type": "file",
            })

        with self.assertRaises(ValidationError):
            RepositoryDocumentation.model_validate({
                **self.payload,
                "repository_summary": "Too short",
            })

    async def test_live_public_repository_generation(self):
        if os.getenv("OPENFORGE_RUN_LIVE_DOC_TEST") != "1":
            self.skipTest("Set OPENFORGE_RUN_LIVE_DOC_TEST=1 to call GitHub and Groq")

        tools = await get_openforge_tools()
        self.assertTrue(tools, "No GitHub MCP tools were loaded")

        agent = DocumentationAgent(tools)
        request = {
            "repository": {
                "repo_url": os.getenv(
                    "OPENFORGE_TEST_REPO_URL",
                    "https://github.com/psf/requests",
                ),
                "analysis_depth": "basic",
                "output_mode": "json",
            },
            "explanation_type": "repository",
            "target_audience": "beginner",
            "max_words": 500,
        }
        validated_request = DocAgentRequest.model_validate(request)
        owner, repository = agent._repository_parts(validated_request)
        documentation = await agent.generate(validated_request)

        self.assertEqual(documentation.repository_name, f"{owner}/{repository}")
        self.assertGreater(len(documentation.repository_summary), 500)
        self.assertTrue(documentation.main_modules)
        self.assertTrue(documentation.execution_flows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test the documentation agent")
    parser.add_argument(
        "--repo",
        help="Run the live test against a GitHub URL or owner/repo",
    )
    options, unittest_arguments = parser.parse_known_args()

    repository_input = options.repo
    if repository_input is None and sys.stdin.isatty():
        repository_input = input(
            "GitHub repository URL or owner/repo (Enter to skip live test): "
        ).strip()

    if repository_input:
        repository_url = repository_input.strip()
        if "://" not in repository_url:
            repository_url = f"https://github.com/{repository_url.strip('/')}"
        os.environ["OPENFORGE_TEST_REPO_URL"] = repository_url
        os.environ["OPENFORGE_RUN_LIVE_DOC_TEST"] = "1"

    unittest.main(argv=[sys.argv[0], *unittest_arguments])