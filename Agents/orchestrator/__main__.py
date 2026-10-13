import argparse
import asyncio
import uuid
from collections.abc import Callable

from Agents.orchestrator.orchestrator_agent import OrchestratorAgent


def build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(
		prog="python -m Agents.orchestrator",
		description="Start an interactive OpenForge orchestrator session.",
	)
	parser.add_argument("--user-id", help="User identifier for conversation memory")
	parser.add_argument("--session-id", help="Session identifier to resume")
	parser.add_argument("--repository-id", help="Repository identifier, for example acme/project")
	parser.add_argument("--repository-context", help="Optional repository context for the agent")
	return parser


async def run_cli(
	argv: list[str] | None = None,
	*,
	agent: OrchestratorAgent | None = None,
	input_fn: Callable[[str], str] = input,
	output_fn: Callable[[str], None] = print,
) -> int:
	args = build_parser().parse_args(argv)
	user_id = (args.user_id or input_fn("User ID: ")).strip()
	repository_id = (args.repository_id or input_fn("Repository ID (owner/name): ")).strip()
	if not user_id or not repository_id:
		output_fn("User ID and repository ID are required.")
		return 2

	session_id = (args.session_id or uuid.uuid4().hex).strip()
	repository_context = args.repository_context
	if repository_context is None:
		repository_context = input_fn("Repository context (optional): ").strip()
	output_fn(f"Session: {session_id}")
	output_fn("Enter a question. Type 'exit' or 'quit' to end the session.")

	try:
		active_agent = agent or OrchestratorAgent()
	except Exception as error:
		output_fn(f"Could not initialize the orchestrator: {error}")
		return 1

	while True:
		try:
			user_input = input_fn("You: ").strip()
		except EOFError:
			break
		if user_input.casefold() in {"exit", "quit"}:
			break
		if not user_input:
			continue
		try:
			answer = await active_agent.run(
				user_input,
				user_id,
				session_id,
				repository_id,
				repository_context,
			)
		except Exception as error:
			output_fn(f"Request failed: {error}")
			continue
		output_fn(f"OpenForge: {answer}")
	return 0


def main() -> None:
	raise SystemExit(asyncio.run(run_cli()))


if __name__ == "__main__":
	main()