import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

project_root = str(Path(__file__).resolve().parents[1])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from Agents.PR_reviewer.pr_reviewer_agent import PRReviewerAgent
from Agents.mentor.mentor_agent import MentorAgent


class FakeLLM:
    def __init__(self, payload):
        self.payload = payload
        self.messages = None

    async def ainvoke(self, messages):
        self.messages = messages
        return SimpleNamespace(content=json.dumps(self.payload))


class FakeTool:
    args_schema = None

    def __init__(self, result, name="get_pull_request"):
        self.name = name
        self.result = result
        self.arguments = None

    async def ainvoke(self, arguments):
        self.arguments = arguments
        return self.result


class MentorAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_mentor_returns_profile_aware_guidance(self):
        llm = FakeLLM({
            "issue_summary": "Add input validation.",
            "learning_objectives": ["Understand request validation"],
            "concepts": ["Pydantic models"],
            "approach_steps": ["Find the request schema", "Add a focused test"],
            "first_task": "Locate the endpoint request model.",
            "suggested_commands": ["pytest -q"],
            "likely_pitfalls": ["Keep existing defaults compatible"],
            "follow_up_questions": [],
        })
        agent = MentorAgent(llm=llm)

        result = await agent.mentor(
            question="How should I start?",
            repository_context="The API uses Pydantic request models in schemas/.",
            profile={"experience_level": "beginner", "skills": "Python, pytest"},
            issue={"title": "Validate input", "body": "Reject malformed payloads."},
        )

        self.assertEqual(result.first_task, "Locate the endpoint request model.")
        self.assertIn('"experience_level": "beginner"', llm.messages)

    async def test_mentor_requires_question_and_repository_context(self):
        agent = MentorAgent(llm=FakeLLM({}))
        with self.assertRaisesRegex(ValueError, "question is required"):
            await agent.mentor("  ", "repository context")


class PRReviewerAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_reviews_supplied_diff_into_structured_findings(self):
        llm = FakeLLM({
            "summary": "The change can return an uninitialized value.",
            "findings": [{
                "severity": "high",
                "title": "Initialize the result before returning",
                "body": "This branch reaches the return without assigning result.",
                "file": "src/example.py",
                "line": 14,
                "suggestion": "Assign a default before the conditional.",
            }],
            "tests_to_run": ["pytest -q"],
            "recommendation": "needs_changes",
        })
        agent = PRReviewerAgent(llm=llm)

        result = await agent.review(
            "acme", "demo", 12, diff="diff --git a/src/example.py b/src/example.py\n+return result"
        )

        self.assertEqual(result.findings[0].severity, "high")
        self.assertEqual(result.findings[0].line, 14)

    async def test_fetches_diff_from_read_only_pull_request_tool(self):
        tool = FakeTool({
            "title": "Handle empty input",
            "files": [{"filename": "src/app.py", "patch": "@@ -1 +1 @@\n-return None\n+return []"}],
        })
        llm = FakeLLM({
            "summary": "No actionable defects found.",
            "findings": [],
            "tests_to_run": [],
            "recommendation": "approve",
        })
        agent = PRReviewerAgent(github_tools=[tool], llm=llm)

        result = await agent.review("acme", "demo", 7)

        self.assertEqual(tool.arguments["pull_number"], 7)
        self.assertIn("return []", llm.messages)
        self.assertEqual(result.recommendation, "approve")

    async def test_combines_pull_request_metadata_with_file_patches(self):
        pull_request_tool = FakeTool({"title": "Handle empty input"})
        files_tool = FakeTool(
            [{"filename": "src/app.py", "patch": "@@ -1 +1 @@\n-return None\n+return []"}],
            name="get_pull_request_files",
        )
        llm = FakeLLM({
            "summary": "No actionable defects found.",
            "findings": [],
            "tests_to_run": [],
            "recommendation": "approve",
        })
        agent = PRReviewerAgent(
            github_tools=[pull_request_tool, files_tool],
            llm=llm,
        )

        await agent.review("acme", "demo", 8)

        self.assertEqual(files_tool.arguments["pull_number"], 8)
        self.assertIn("Handle empty input", llm.messages)
        self.assertIn("return []", llm.messages)

    async def test_requires_diff_when_tool_response_has_no_patch(self):
        agent = PRReviewerAgent(
            github_tools=[FakeTool({"title": "Metadata only"})],
            llm=FakeLLM({}),
        )
        with self.assertRaisesRegex(ValueError, "did not include a diff"):
            await agent.review("acme", "demo", 7)


if __name__ == "__main__":
    unittest.main()