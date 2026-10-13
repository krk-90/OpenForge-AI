import json
import os
from typing import Any

from pydantic import BaseModel, Field

from Agents.profile.profile_agent import DeveloperProfile
from APP.core.tracing import trace_step
from APP.core.resilience import invoke_with_retry


class MentorGuidance(BaseModel):
    issue_summary: str
    learning_objectives: list[str] = Field(default_factory=list)
    concepts: list[str] = Field(default_factory=list)
    approach_steps: list[str] = Field(default_factory=list)
    first_task: str
    suggested_commands: list[str] = Field(default_factory=list)
    likely_pitfalls: list[str] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)


class MentorAgent:
    def __init__(self, llm=None):
        if llm is None:
            from langchain_groq import ChatGroq

            llm = ChatGroq(
                model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
                temperature=0,
            )
        self.llm = llm

    @trace_step("process.mentor")
    async def mentor(
        self,
        question: str,
        repository_context: str,
        profile: dict[str, Any] | DeveloperProfile | None = None,
        issue: dict[str, Any] | str | None = None,
    ) -> MentorGuidance:
        if not question.strip():
            raise ValueError("question is required")
        if not repository_context.strip():
            raise ValueError("repository_context is required")

        if isinstance(profile, dict):
            profile = DeveloperProfile.model_validate(profile)

        prompt = f"""
You are the OpenForge contribution mentor. Help the contributor understand the work
and make progress themselves. Do not invent repository files, APIs, or commands;
ground suggestions in the supplied context and label uncertainty explicitly.
Adapt explanations to the contributor's experience. Return only JSON matching this
shape:
{{
  "issue_summary": "",
  "learning_objectives": [],
  "concepts": [],
  "approach_steps": [],
  "first_task": "",
  "suggested_commands": [],
  "likely_pitfalls": [],
  "follow_up_questions": []
}}

Contributor profile:
{json.dumps(profile.model_dump() if profile else {}, indent=2)}

Issue:
{json.dumps(issue, indent=2) if isinstance(issue, (dict, list)) else issue or "Not provided"}

Repository context:
{repository_context}

Contributor question:
{question}
"""
        response = await invoke_with_retry(self.llm, prompt, operation="mentor")
        content = response.content if hasattr(response, "content") else response
        if not isinstance(content, (str, bytes, bytearray)):
            raise TypeError("Mentor model returned a non-text response")
        return MentorGuidance.model_validate_json(content)