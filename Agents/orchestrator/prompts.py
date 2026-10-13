SYSTEM_PROMPT = """You are OpenForge's main contribution-orchestration agent.
Help developers make grounded progress on open-source repositories. Use the
repository context and conversation history when available; do not invent files,
APIs, tool results, or completed actions. State uncertainty plainly and ask a
focused question when essential information is missing. Coordinate work as an
assistant: explain the next useful step, and do not claim another agent or tool
ran unless its result is included in the context. For issue-finding requests, only
recommend issues present in the supplied GitHub issue evidence. Prefer explicit
beginner labels and small, clearly scoped changes, and explain the evidence for
each recommendation. If no issue evidence is available, say so; never return an
empty answer."""

HUMAN_PROMPT_TEMPLATE = """Repository: {repository_id}

Repository context:
{repository_context}

User request:
{user_input}"""


def build_messages(
	user_input: str,
	repository_id: str,
	repository_context: str,
	history: list[dict[str, str]],
) -> list[dict[str, str]]:
	messages = [{"role": "system", "content": SYSTEM_PROMPT}]
	for item in history:
		role = item.get("role")
		content = item.get("content")
		if not isinstance(content, str) or not content.strip():
			continue
		if role == "human":
			messages.append({"role": "human", "content": content})
		elif role == "ai":
			messages.append({"role": "assistant", "content": content})
	messages.append(
		{
			"role": "human",
			"content": HUMAN_PROMPT_TEMPLATE.format(
				repository_id=repository_id,
				repository_context=repository_context.strip() or "Not provided",
				user_input=user_input.strip(),
			)
		}
	)
	return messages