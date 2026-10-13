import json
import os
from typing import Any, Literal

from pydantic import BaseModel, Field

from APP.core.tracing import trace_step


class PRReviewFinding(BaseModel):
    severity: Literal["critical", "high", "medium", "low", "info"]
    title: str
    body: str
    file: str | None = None
    line: int | None = Field(default=None, ge=1)
    suggestion: str = ""


class PRReviewResult(BaseModel):
    summary: str
    findings: list[PRReviewFinding] = Field(default_factory=list)
    tests_to_run: list[str] = Field(default_factory=list)
    recommendation: Literal["needs_changes", "approve_with_nits", "approve"]


class PRReviewerAgent:
    _PR_READ_TOOL_NAMES = ("get_pull_request", "pull_request_read")
    _PR_FILES_TOOL_NAMES = ("get_pull_request_files", "pull_request_files")

    def __init__(self, github_tools=(), llm=None):
        self.tools = github_tools
        if llm is None:
            from langchain_groq import ChatGroq

            llm = ChatGroq(
                model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
                temperature=0,
            )
        self.llm = llm

    def _find_tool(self, names: tuple[str, ...]):
        return next((tool for tool in self.tools if tool.name in names), None)

    @staticmethod
    def _tool_arguments(tool, arguments: dict[str, Any]) -> dict[str, Any]:
        schema = getattr(tool, "args_schema", None)
        if isinstance(schema, dict):
            fields = schema.get("properties", {})
        else:
            fields = getattr(schema, "model_fields", None)
            if fields is None:
                fields = getattr(schema, "__fields__", None)
        if fields:
            return {name: value for name, value in arguments.items() if name in fields}
        return arguments

    @staticmethod
    def _unwrap_result(result: Any) -> Any:
        if isinstance(result, list):
            text = "\n".join(
                item["text"]
                for item in result
                if isinstance(item, dict)
                and item.get("type") == "text"
                and isinstance(item.get("text"), str)
            )
            if text:
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return text
        if isinstance(result, dict):
            for key in ("content", "data", "pull_request"):
                if key in result:
                    unwrapped = PRReviewerAgent._unwrap_result(result[key])
                    if unwrapped is not result[key]:
                        return unwrapped
            text = result.get("text")
            if isinstance(text, str):
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return text
        if isinstance(result, str):
            try:
                return json.loads(result)
            except json.JSONDecodeError:
                return result
        return result

    @trace_step("pr_review.fetch_github_context")
    async def _fetch_pull_request(self, owner: str, repo: str, pull_number: int):
        arguments = {
            "owner": owner,
            "repo": repo,
            "pull_number": pull_number,
            "pullNumber": pull_number,
        }
        pull_request_tool = self._find_tool(self._PR_READ_TOOL_NAMES)
        files_tool = self._find_tool(self._PR_FILES_TOOL_NAMES)
        if pull_request_tool is None and files_tool is None:
            raise RuntimeError(
                "A pull request diff is required when no GitHub pull-request read tool is available"
            )

        pull_request = None
        if pull_request_tool is not None:
            result = await pull_request_tool.ainvoke(
                self._tool_arguments(pull_request_tool, arguments)
            )
            pull_request = self._unwrap_result(result)

        if files_tool is not None:
            result = await files_tool.ainvoke(
                self._tool_arguments(files_tool, arguments)
            )
            files = self._unwrap_result(result)
            if isinstance(pull_request, dict):
                if not pull_request.get("files"):
                    pull_request = {**pull_request, "files": files}
            elif pull_request is None:
                pull_request = {"files": files}
        return pull_request

    @staticmethod
    def _extract_diff(pull_request: Any) -> tuple[str, str]:
        if isinstance(pull_request, str):
            if "diff --git " in pull_request or pull_request.startswith("@@"):
                return "", pull_request
            return pull_request, ""
        if isinstance(pull_request, list):
            pull_request = {"files": pull_request}
        if not isinstance(pull_request, dict):
            return "", ""

        title = str(pull_request.get("title") or "")
        diff = pull_request.get("diff") or pull_request.get("patch") or ""
        if isinstance(diff, str) and diff.strip():
            return title, diff

        files = pull_request.get("files")
        if isinstance(files, dict):
            files = files.get("files", files.get("data", []))
        if isinstance(files, list):
            patches = []
            for file in files:
                if not isinstance(file, dict) or not isinstance(file.get("patch"), str):
                    continue
                filename = file.get("filename") or file.get("path") or "unknown file"
                patches.append(f"File: {filename}\n{file['patch']}")
            return title, "\n\n".join(patches)
        return title, ""

    @trace_step("process.pr_review")
    async def review(
        self,
        owner: str,
        repo: str,
        pull_number: int,
        diff: str | None = None,
        additional_context: str = "",
    ) -> PRReviewResult:
        if not owner.strip() or not repo.strip():
            raise ValueError("owner and repo are required")
        if pull_number < 1:
            raise ValueError("pull_number must be positive")

        title = ""
        review_diff = diff or ""
        if not review_diff.strip():
            pull_request = await self._fetch_pull_request(owner, repo, pull_number)
            title, review_diff = self._extract_diff(pull_request)
        if not review_diff.strip():
            raise ValueError(
                "The GitHub response did not include a diff; pass diff explicitly or provide a tool response with file patches"
            )

        prompt = f"""
Review this pull request as a senior software engineer. Report only actionable
defects introduced by the change, prioritize by severity, and cite exact changed
file/line locations when the diff supports them. Do not invent runtime behavior.
If there are no defects, return an empty findings list. The review is advisory:
do not claim to have posted a review or changed GitHub state. Return only JSON:
{{
  "summary": "",
  "findings": [
    {{"severity":"medium","title":"","body":"","file":null,"line":null,"suggestion":""}}
  ],
  "tests_to_run": [],
  "recommendation": "approve_with_nits"
}}

Pull request: {owner}/{repo}#{pull_number}
Title: {title or "Not provided"}
Additional context:
{additional_context or "Not provided"}

Diff:
{review_diff}
"""
        response = await self.llm.ainvoke(prompt)
        content = response.content if hasattr(response, "content") else response
        if not isinstance(content, (str, bytes, bytearray)):
            raise TypeError("Review model returned a non-text response")
        return PRReviewResult.model_validate_json(content)