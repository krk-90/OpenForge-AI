import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

project_root = str(Path(__file__).resolve().parents[1])
if project_root not in sys.path:
	sys.path.insert(0, project_root)

from Agents.orchestrator.orchestrator_agent import OrchestratorAgent
from Agents.orchestrator.__main__ import run_cli


class FakeLLM:
	def __init__(self, content):
		self.content = content
		self.messages = None

	async def ainvoke(self, messages):
		self.messages = messages
		return SimpleNamespace(content=self.content)


class FakeIssueTool:
	name = "list_issues"
	args_schema = {"properties": {"owner": {}, "repo": {}, "state": {}, "perPage": {}}}

	def __init__(self, result):
		self.result = result
		self.arguments = None

	async def ainvoke(self, arguments):
		self.arguments = arguments
		return self.result


class FakeAgent:
	def __init__(self):
		self.calls = []

	async def run(self, *args):
		self.calls.append(args)
		return "A grounded answer."


class OrchestratorAgentTests(unittest.IsolatedAsyncioTestCase):
	async def test_cli_forwards_interactive_input_to_agent(self):
		inputs = iter(["user-1", "acme/demo", "Routes live under app/routes.", "How do I start?", "exit"])
		outputs = []
		agent = FakeAgent()

		result = await run_cli(
			[],
			agent=agent,
			input_fn=lambda _prompt: next(inputs),
			output_fn=outputs.append,
		)

		self.assertEqual(result, 0)
		self.assertEqual(len(agent.calls), 1)
		self.assertEqual(agent.calls[0][0], "How do I start?")
		self.assertEqual(agent.calls[0][0 + 1:5], ("user-1", agent.calls[0][2], "acme/demo", "Routes live under app/routes."))
		self.assertIn("OpenForge: A grounded answer.", outputs)

	async def test_builds_role_structured_prompt_and_persists_memory(self):
		llm = FakeLLM("Start by locating the relevant route and test.")
		stored = {}
		agent = OrchestratorAgent(
			llm=llm,
			memory_loader=lambda user_id, session_id: [
				{"role": "human", "content": "I am new to this repo."},
				{"role": "ai", "content": "We can take it one step at a time."},
			],
			memory_saver=lambda *args: stored.update({"args": args}),
		)

		result = await agent.run(
			"How should I start?",
			"user-1",
			"session-1",
			"acme/demo",
			repository_context="Routes live under app/routes.",
		)

		self.assertEqual(result, llm.content)
		self.assertEqual([message["role"] for message in llm.messages], [
			"system", "human", "assistant", "human"
		])
		self.assertIn("Routes live under app/routes.", llm.messages[3]["content"])
		self.assertEqual(stored["args"][:3], ("user-1", "session-1", "acme/demo"))
		self.assertEqual(stored["args"][3][-1], {"role": "ai", "content": llm.content})

	async def test_issue_request_fetches_open_issues_for_selected_repository(self):
		llm = FakeLLM("Issue #12 is a good first contribution because it is scoped.")
		tool = FakeIssueTool({"issues": [{
			"number": 12,
			"title": "Document local setup",
			"labels": [{"name": "good first issue"}],
			"body": "Add the missing local setup steps.",
			"html_url": "https://github.com/acme/demo/issues/12",
		}]})
		agent = OrchestratorAgent(
			llm=llm,
			github_tools=[tool],
			memory_loader=lambda *_args: [],
			memory_saver=lambda *_args: None,
		)

		await agent.run(
			"Find me a good first issue.", "user-1", "session-1",
			"https://github.com/acme/demo.git",
		)

		self.assertEqual(tool.arguments["owner"], "acme")
		self.assertEqual(tool.arguments["repo"], "demo")
		self.assertEqual(tool.arguments["state"], "open")
		self.assertIn('"number": 12', llm.messages[-1]["content"])
		self.assertIn("good first issue", llm.messages[-1]["content"])

	async def test_issue_request_explains_when_github_tools_are_unavailable(self):
		saved = []
		agent = OrchestratorAgent(
			llm=FakeLLM("unused"),
			memory_loader=lambda *_args: [],
			memory_saver=lambda *args: saved.append(args),
		)

		answer = await agent.run(
			"Find a good first issue.", "user-1", "session-1", "acme/demo",
		)

		self.assertIn("GitHub issue lookup is unavailable", answer)
		self.assertEqual(len(saved), 1)

	async def test_empty_model_response_is_not_persisted(self):
		saved = []
		agent = OrchestratorAgent(
			llm=FakeLLM(" "),
			memory_loader=lambda *_args: [],
			memory_saver=lambda *args: saved.append(args),
		)

		with self.assertRaisesRegex(RuntimeError, "empty response"):
			await agent.run("How do I start?", "user-1", "session-1", "acme/demo")
		self.assertEqual(saved, [])

	async def test_requires_non_empty_user_input(self):
		agent = OrchestratorAgent(llm=FakeLLM("answer"))
		with self.assertRaisesRegex(ValueError, "user_input is required"):
			await agent.run(" ", "user-1", "session-1", "acme/demo")


if __name__ == "__main__":
	unittest.main()