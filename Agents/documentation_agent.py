import asyncio
import html
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

from langchain_core.messages import HumanMessage
from langchain_groq import ChatGroq

project_root = str(Path(__file__).resolve().parents[1])
if project_root not in sys.path:
	sys.path.insert(0, project_root)

from DATABASE.supabase_db import (
	get_generated_documentation,
	save_generated_documentation,
)
from schemas.repo import (
	DocAgentRequest,
	DocumentationValidator,
	RepositoryDocumentation,
)


class DocumentationAgent:
	_MAX_TREE_ENTRIES = 60
	_MAX_SOURCE_FILES = 8
	_MAX_FILE_CHARS = 1800
	_MAX_CONTEXT_CHARS = 10000

	def __init__(self, github_tools, llm=None):
		self.tools = github_tools
		self.llm = llm or ChatGroq(
			model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
			temperature=0,
			max_tokens=4096,
		)

	def _find_tool(self, name: str):
		return next(
			(tool for tool in self.tools if tool.name == name),
			None,
		)

	@staticmethod
	def _supported_arguments(tool, arguments: dict):
		schema = getattr(tool, "args_schema", None)
		if isinstance(schema, dict):
			fields = schema.get("properties", {})
			return {
				name: value
				for name, value in arguments.items()
				if name in fields
			}
		fields = getattr(schema, "model_fields", None)
		if fields is None:
			fields = getattr(schema, "__fields__", None)
		if fields:
			return {
				name: value
				for name, value in arguments.items()
				if name in fields
			}
		return arguments

	async def _invoke_tool(self, name: str, arguments: dict):
		tool = self._find_tool(name)
		if tool is None:
			raise RuntimeError(f"Required GitHub MCP tool is unavailable: {name}")
		result = await tool.ainvoke(
			self._supported_arguments(tool, arguments)
		)
		return self._unwrap_result(result)

	@classmethod
	def _unwrap_result(cls, result):
		if isinstance(result, list):
			text_blocks = [
				item["text"]
				for item in result
				if isinstance(item, dict)
				and item.get("type") == "text"
				and isinstance(item.get("text"), str)
			]
			if text_blocks:
				text = "\n".join(text_blocks)
				try:
					return json.loads(text)
				except json.JSONDecodeError:
					return text
		if isinstance(result, dict):
			content = result.get("content")
			if isinstance(content, list):
				return cls._unwrap_result(content)
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

	@staticmethod
	def _repository_parts(request: DocAgentRequest) -> tuple[str, str]:
		path_parts = [
			part
			for part in urlsplit(str(request.repository.repo_url)).path.split("/")
			if part
		]
		if len(path_parts) < 2:
			raise ValueError("repo_url must include an owner and repository name")
		return path_parts[0], path_parts[1].removesuffix(".git")

	@staticmethod
	def _tree_entries(tree):
		if isinstance(tree, dict):
			tree = tree.get("tree", tree.get("files", tree.get("items", [])))
		if isinstance(tree, list):
			return [entry for entry in tree if isinstance(entry, dict)]
		return []

	async def _load_repository_tree(
		self,
		owner: str,
		repository: str,
		request: DocAgentRequest,
	):
		ref = request.repository.commit_sha or request.repository.branch
		arguments = {
			"owner": owner,
			"repo": repository,
			"branch": request.repository.branch,
			"ref": ref,
			"sha": ref,
			"tree_sha": ref,
			"recursive": True,
			"path": request.target_path or "",
		}
		if self._find_tool("get_tree"):
			return await self._invoke_tool("get_tree", arguments)

		return await self._invoke_tool(
			"get_file_contents",
			{
				"owner": owner,
				"repo": repository,
				"path": request.target_path or "",
				"branch": ref,
			},
		)

	@staticmethod
	def _file_priority(path: str) -> tuple[int, int, str]:
		name = path.rsplit("/", 1)[-1].lower()
		if name.startswith("readme"):
			priority = 0
		elif name in {
			"pyproject.toml",
			"package.json",
			"requirements.txt",
			"go.mod",
			"cargo.toml",
			"dockerfile",
		}:
			priority = 1
		else:
			priority = 2
		return priority, path.count("/"), path.lower()

	def _select_file_paths(self, entries, request: DocAgentRequest) -> list[str]:
		supported_suffixes = {
			".c", ".cpp", ".cs", ".go", ".java", ".js", ".jsx",
			".md", ".py", ".rs", ".sh", ".sql", ".toml", ".ts",
			".tsx", ".txt", ".yaml", ".yml", ".json",
		}
		target = (request.target_path or "").replace("\\", "/").strip("/")
		if ":" in target and request.explanation_type in {"class", "function"}:
			target = target.split(":", 1)[0]

		paths = []
		for entry in entries:
			path = entry.get("path")
			if not isinstance(path, str):
				continue
			if entry.get("type") not in (None, "blob", "file"):
				continue
			if Path(path).suffix.lower() not in supported_suffixes:
				continue
			if any(part in {".git", "node_modules", "dist", "build"} for part in path.split("/")):
				continue
			size = entry.get("size")
			if isinstance(size, int) and size > 200000:
				continue
			if request.explanation_type == "folder" and target:
				if not path.startswith(f"{target}/"):
					continue
			elif request.explanation_type in {"file", "class", "function"} and target:
				if path != target and not path.startswith(f"{target}/"):
					continue
			paths.append(path)

		if not paths:
			paths = [
				"README.md",
				"pyproject.toml",
				"requirements.txt",
				"package.json",
				"src/main.py",
				"main.py",
			]
		return sorted(paths, key=self._file_priority)[: self._MAX_SOURCE_FILES]

	async def _collect_source_files(
		self,
		owner: str,
		repository: str,
		request: DocAgentRequest,
		entries,
	) -> list[dict[str, str]]:
		file_tool = self._find_tool("get_file_contents")
		if file_tool is None:
			raise RuntimeError("Required GitHub MCP tool is unavailable: get_file_contents")

		source_files = []
		context_size = 0
		ref = request.repository.commit_sha or request.repository.branch
		for path in self._select_file_paths(entries, request):
			arguments = {
				"owner": owner,
				"repo": repository,
				"path": path,
				"ref": ref,
				"branch": request.repository.branch,
				"sha": ref,
				"commit_sha": request.repository.commit_sha,
			}
			try:
				result = await file_tool.ainvoke(
					self._supported_arguments(file_tool, arguments)
				)
			except Exception:
				continue
			result = self._unwrap_result(result)
			if isinstance(result, dict):
				result = result.get("content", result.get("text", result))
			if not isinstance(result, str):
				result = json.dumps(result, ensure_ascii=False, default=str)

			remaining = self._MAX_CONTEXT_CHARS - context_size
			if remaining <= 0:
				break
			text = result[: min(self._MAX_FILE_CHARS, remaining)]
			source_files.append({"path": path, "content": text})
			context_size += len(text)

		return source_files

	def _build_prompt(
		self,
		request: DocAgentRequest,
		owner: str,
		repository: str,
		entries,
		source_files,
	) -> str:
		context = {
			"repository_tree": entries[: self._MAX_TREE_ENTRIES],
			"source_files": source_files,
		}
		return f"""Create repository documentation using only evidence in the supplied repository context.

Repository: {owner}/{repository}
Branch: {request.repository.commit_sha or request.repository.branch}
Explanation type: {request.explanation_type}
Target path: {request.target_path or "(entire repository)"}
Audience: {request.target_audience}
Maximum words: {request.max_words}
Include diagrams: {request.include_diagrams}
Include contributor guide: {request.include_contributor_guide}
Include improvement suggestions: {request.include_improvements}

Do not invent files, dependencies, behaviors, or execution flows. State uncertainty where the context is insufficient. Keep the repository_summary over 500 characters. Include at least one main module, folder, and execution flow. When an inclusion option is false, use an empty list for that section; keep the contributor_guide object but use empty values when it is disabled. Set generated_word_count to a non-negative integer.

Return only one JSON object matching this JSON Schema:
{json.dumps(RepositoryDocumentation.model_json_schema(), indent=2)}

Repository context:
{json.dumps(context, indent=2, ensure_ascii=False, default=str)}
"""

	@staticmethod
	def _response_json(response):
		content = getattr(response, "content", response)
		if isinstance(content, list):
			content = "\n".join(
				item.get("text", "")
				for item in content
				if isinstance(item, dict)
			)
		if not isinstance(content, (str, bytes, bytearray, dict)):
			raise TypeError("The documentation model returned an unsupported response")
		if isinstance(content, str):
			content = content.strip()
			if content.startswith("```"):
				content = content.split("\n", 1)[-1]
				if content.endswith("```"):
					content = content[:-3].strip()
		return content

	async def generate(
		self,
		request: DocAgentRequest | dict,
	) -> RepositoryDocumentation:
		request = DocAgentRequest.model_validate(request)
		owner, repository = self._repository_parts(request)
		ref = request.repository.commit_sha or request.repository.branch
		tree = await self._load_repository_tree(owner, repository, request)
		entries = self._tree_entries(tree)
		source_files = await self._collect_source_files(
			owner,
			repository,
			request,
			entries,
		)
		prompt = self._build_prompt(
			request,
			owner,
			repository,
			entries,
			source_files,
		)
		response = await self.llm.ainvoke([HumanMessage(content=prompt)])
		documentation = DocumentationValidator.validate(
			self._response_json(response)
		)
		documentation.repository_name = f"{owner}/{repository}"
		return documentation

	async def run(self, request: DocAgentRequest | dict) -> str:
		request = DocAgentRequest.model_validate(request)
		documentation = await self.generate(request)
		owner, repository = self._repository_parts(request)
		repository_name = f"{owner}/{repository}"
		generated_document = self.format_documentation(
			documentation,
			request.repository.output_mode,
		)
		save_generated_documentation(
			repository_name,
			generated_document,
			request.repository.output_mode,
		)
		stored_document = get_generated_documentation(repository_name)
		if not stored_document or not isinstance(stored_document.get("document"), str):
			raise RuntimeError(
				f"Documentation for {repository_name} was not returned by Supabase"
			)
		return stored_document["document"]

	@staticmethod
	def format_documentation(
		documentation: RepositoryDocumentation | dict,
		output_mode: str = "markdown",
	) -> str:
		doc = DocumentationValidator.validate(documentation)
		if output_mode == "json":
			return json.dumps(doc.model_dump(), indent=2, ensure_ascii=False)

		if output_mode == "markdown":
			lines = [
				f"# {doc.repository_name}",
				"",
				doc.repository_summary,
				"",
				"## Architecture Overview",
				"",
				doc.architecture_overview,
				"",
				"## Tech Stack",
				"",
				*[f"- {item}" for item in doc.tech_stack],
				"",
				"## Main Modules",
				"",
				*[f"- {item}" for item in doc.main_modules],
				"",
				"## Folders",
				"",
			]
			for folder in doc.folders:
				lines.extend([
					f"### `{folder.path}`",
					"",
					folder.purpose,
					"",
					*[f"- {item}" for item in folder.responsibilities],
					"",
					"Important files: " + ", ".join(f"`{item}`" for item in folder.important_files),
					"",
				])
			lines.extend(["## Files", ""])
			for file_summary in doc.files:
				lines.extend([
					f"### `{file_summary.path}`",
					"",
					file_summary.summary,
					"",
					f"Purpose: {file_summary.purpose}",
					"",
				])
			lines.extend(["## Execution Flows", ""])
			for flow in doc.execution_flows:
				lines.extend([
					f"### {flow.name}",
					"",
					flow.description,
					"",
					*[f"{index}. {step}" for index, step in enumerate(flow.flow_steps, 1)],
					"",
				])
			lines.extend([
				"## Diagrams",
				"",
				*[f"```\n{diagram}\n```" for diagram in doc.diagrams],
				"",
				"## Contributor Guide",
				"",
				f"Difficulty: {doc.contributor_guide.difficulty}",
				"",
				*[f"- {item}" for item in doc.contributor_guide.starting_points],
				*[f"- Suggested issue: {item}" for item in doc.contributor_guide.suggested_issues],
				"",
				"## Improvement Suggestions",
				"",
				*[f"- {item}" for item in doc.improvement_suggestions],
				"",
				f"Generated word count: {doc.generated_word_count}",
			])
			return "\n".join(lines)

		if output_mode == "html":
			escape = html.escape
			folders = "".join(
				f"<li><strong>{escape(folder.path)}</strong>: {escape(folder.purpose)}"
				"<ul>"
				+ "".join(
					f"<li>{escape(item)}</li>"
					for item in folder.responsibilities
				)
				+ "</ul><p>Important files: "
				+ escape(", ".join(folder.important_files))
				+ "</p></li>"
				for folder in doc.folders
			)
			files = "".join(
				f"<li><h3>{escape(file_summary.path)}</h3>"
				f"<p>{escape(file_summary.purpose)}</p>"
				f"<p>{escape(file_summary.summary)}</p>"
				"<ul>"
				+ "".join(
					f"<li>{escape(label)}: {escape(', '.join(values))}</li>"
					for label, values in (
						("Classes", file_summary.classes),
						("Functions", file_summary.functions),
						("Dependencies", file_summary.dependencies),
					)
				)
				+ "</ul></li>"
				for file_summary in doc.files
			)
			flows = "".join(
				"<li><strong>"
				+ escape(flow.name)
				+ "</strong>: "
				+ escape(flow.description)
				+ "<ol>"
				+ "".join(f"<li>{escape(step)}</li>" for step in flow.flow_steps)
				+ "</ol></li>"
				for flow in doc.execution_flows
			)
			diagrams = "".join(
				f"<pre><code>{escape(diagram)}</code></pre>"
				for diagram in doc.diagrams
			)
			guide = (
				f"<p>Difficulty: {escape(doc.contributor_guide.difficulty)}</p>"
				"<h3>Starting Points</h3><ul>"
				+ "".join(
					f"<li>{escape(item)}</li>"
					for item in doc.contributor_guide.starting_points
				)
				+ "</ul><h3>Suggested Issues</h3><ul>"
				+ "".join(
					f"<li>{escape(item)}</li>"
					for item in doc.contributor_guide.suggested_issues
				)
				+ "</ul>"
			)
			improvements = "".join(
				f"<li>{escape(item)}</li>"
				for item in doc.improvement_suggestions
			)
			return "".join([
				"<!doctype html><html><head><meta charset=\"utf-8\"><title>",
				escape(doc.repository_name),
				"</title></head><body><main><h1>",
				escape(doc.repository_name),
				"</h1><p>",
				escape(doc.repository_summary),
				"</p><h2>Architecture Overview</h2><p>",
				escape(doc.architecture_overview),
				"</p><h2>Tech Stack</h2><ul>",
				"".join(f"<li>{escape(item)}</li>" for item in doc.tech_stack),
				"</ul><h2>Main Modules</h2><ul>",
				"".join(f"<li>{escape(item)}</li>" for item in doc.main_modules),
				"</ul><h2>Folders</h2><ul>",
				folders,
				"</ul><h2>Files</h2><ul>",
				files,
				"</ul><h2>Execution Flows</h2><ul>",
				flows,
				"</ul><h2>Diagrams</h2>",
				diagrams,
				"<h2>Contributor Guide</h2>",
				guide,
				"<h2>Improvement Suggestions</h2><ul>",
				improvements,
				"</ul><p>Generated word count: ",
				str(doc.generated_word_count),
				"</p></main></body></html>",
			])

		raise ValueError(f"Unsupported documentation output mode: {output_mode}")


async def main():
	from MCP_server.server.github_git_server import get_openforge_tools

	repository_input = input("GitHub repository URL or owner/repo: ").strip()
	if not repository_input:
		print("No repository provided; documentation was not generated.")
		return

	repository_url = repository_input
	if "://" not in repository_url:
		repository_url = f"https://github.com/{repository_url.strip('/')}"

	request = DocAgentRequest.model_validate({
		"repository": {
			"repo_url": repository_url,
			"analysis_depth": "basic",
			"output_mode": "markdown",
		},
		"explanation_type": "repository",
		"target_audience": "beginner",
		"max_words": 1500,
	})
	tools = await get_openforge_tools()
	if not tools:
		raise RuntimeError("No GitHub MCP tools are available; check GITHUB_TOKEN and MCP setup.")

	agent = DocumentationAgent(tools)
	documentation = await agent.run(request)
	print(documentation)


if __name__ == "__main__":
	try:
		asyncio.run(main())
	except Exception as error:
		print(f"Documentation generation failed: {error}", file=sys.stderr)
		sys.exit(1)