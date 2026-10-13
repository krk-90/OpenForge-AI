from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

DEFAULT_DATASET = Path(__file__).with_name("dataset.json")


class EvaluationError(RuntimeError):
	pass


class ApiClient:
	def __init__(self, base_url: str, token: str, timeout: float = 90):
		self.base_url = base_url.rstrip("/") + "/"
		self.token = token
		self.timeout = timeout

	def request(self, method: str, path: str, body: dict[str, Any] | None = None):
		url = urljoin(self.base_url, path.lstrip("/"))
		data = None if body is None else json.dumps(body).encode("utf-8")
		request = Request(
			url,
			data=data,
			method=method.upper(),
			headers={
				"Accept": "application/json",
				"Authorization": f"Bearer {self.token}",
				"Content-Type": "application/json",
			},
		)
		try:
			with urlopen(request, timeout=self.timeout) as response:
				return response.status, _decode_response(response.read())
		except HTTPError as error:
			return error.code, _decode_response(error.read())
		except (URLError, TimeoutError, OSError) as error:
			raise EvaluationError(f"Request to {path} failed: {error}") from error


def _decode_response(body: bytes) -> Any:
	if not body:
		return None
	try:
		return json.loads(body.decode("utf-8"))
	except (UnicodeDecodeError, json.JSONDecodeError):
		return body.decode("utf-8", errors="replace")


def _substitute(value: Any, variables: dict[str, str]) -> Any:
	if isinstance(value, dict):
		return {key: _substitute(item, variables) for key, item in value.items()}
	if isinstance(value, list):
		return [_substitute(item, variables) for item in value]
	if isinstance(value, str):
		for name, replacement in variables.items():
			value = value.replace("{{" + name + "}}", replacement)
	return value


def _get_path(value: Any, path: str) -> Any:
	current = value
	for component in path.split("."):
		if not isinstance(current, dict) or component not in current:
			return None
		current = current[component]
	return current


def evaluate_response(
	case: dict[str, Any],
	status_code: int,
	response: Any,
) -> dict[str, Any]:
	base = {
		"name": case["name"],
		"endpoint": case["path"],
		"status_code": status_code,
	}
	if status_code in case.get("skip_statuses", []):
		return {**base, "status": "skipped", "reason": "Optional integration is unavailable."}
	if status_code != case.get("expected_status", 200):
		detail = response.get("detail", "Unexpected HTTP status") if isinstance(response, dict) else "Unexpected HTTP status"
		return {**base, "status": "failed", "reason": str(detail)}
	if not isinstance(response, dict):
		return {**base, "status": "failed", "reason": "Expected a JSON object response."}

	issues = []
	checks = case.get("checks", {})
	for field in checks.get("required_fields", []):
		if _get_path(response, field) is None:
			issues.append(f"Missing field: {field}")
	for field in checks.get("non_empty_fields", []):
		value = _get_path(response, field)
		if value is None or value == "" or value == []:
			issues.append(f"Empty field: {field}")
	for field, allowed in checks.get("allowed_values", {}).items():
		value = _get_path(response, field)
		if value not in allowed:
			issues.append(f"Unexpected value for {field}: {value!r}")
	for field, expected_terms in checks.get("contains", {}).items():
		value = _get_path(response, field)
		actual = value if isinstance(value, list) else [value]
		actual_terms = {str(item).casefold() for item in actual}
		for term in expected_terms:
			if str(term).casefold() not in actual_terms:
				issues.append(f"{field} did not contain {term!r}")
	for field, minimum in checks.get("min_list_lengths", {}).items():
		value = _get_path(response, field)
		if not isinstance(value, list) or len(value) < minimum:
			issues.append(f"{field} must contain at least {minimum} item(s)")

	return {
		**base,
		"status": "failed" if issues else "passed",
		"checks": issues,
	}


def _build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(
		prog="python -m Evalution.online",
		description="Run live HTTP evaluations against an OpenForge API instance.",
	)
	parser.add_argument(
		"--base-url",
		default=os.getenv("OPENFORGE_API_URL", "http://127.0.0.1:8000"),
		help="OpenForge API base URL",
	)
	parser.add_argument(
		"--token",
		default=os.getenv("OPENFORGE_EVAL_ACCESS_TOKEN"),
		help="Supabase access token; defaults to OPENFORGE_EVAL_ACCESS_TOKEN",
	)
	parser.add_argument(
		"--repository-id",
		default=os.getenv("OPENFORGE_EVAL_REPOSITORY_ID"),
		help="Indexed repository ID (owner/name)",
	)
	parser.add_argument(
		"--repository-url",
		help="GitHub repository URL; defaults from --repository-id",
	)
	parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
	parser.add_argument("--output", type=Path, help="Optional JSON report path")
	parser.add_argument(
		"--keep-session",
		action="store_true",
		help="Keep the generated evaluation chat and transcript",
	)
	return parser


def run_evaluation(args: argparse.Namespace) -> dict[str, Any]:
	if not args.token:
		raise EvaluationError(
			"Provide --token or set OPENFORGE_EVAL_ACCESS_TOKEN to a Supabase access token."
		)
	if not args.repository_id:
		raise EvaluationError(
			"Provide --repository-id or set OPENFORGE_EVAL_REPOSITORY_ID."
		)
	if not args.dataset.is_file():
		raise EvaluationError(f"Evaluation dataset not found: {args.dataset}")

	dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
	repository_url = args.repository_url or f"https://github.com/{args.repository_id}"
	variables = {
		"repository_id": args.repository_id,
		"repository_url": repository_url,
	}
	client = ApiClient(args.base_url, args.token)
	started = time.perf_counter()
	health_status, health_response = client.request("GET", "/health")
	if health_status != 200 or not isinstance(health_response, dict):
		raise EvaluationError(f"API health check failed with HTTP {health_status}.")

	create_status, created = client.request(
		"POST",
		"/agents/sessions",
		{"repository_id": args.repository_id, "title": "OpenForge online evaluation"},
	)
	if create_status != 201 or not isinstance(created, dict):
		raise EvaluationError(f"Could not create evaluation chat (HTTP {create_status}).")
	session = created.get("session")
	if not isinstance(session, dict) or not session.get("session_id"):
		raise EvaluationError("Session creation response did not include session_id.")
	session_id = str(session["session_id"])
	variables["session_id"] = session_id

	results = []
	try:
		for case in dataset.get("cases", []):
			payload = _substitute(case.get("payload", {}), variables)
			case_started = time.perf_counter()
			try:
				method = case.get("method", "POST").upper()
				status_code, response = client.request(
					method,
					case["path"],
					payload if method != "GET" else None,
				)
				result = evaluate_response(case, status_code, response)
			except EvaluationError as error:
				result = {
					"name": case["name"],
					"endpoint": case["path"],
					"status": "failed",
					"reason": str(error),
				}
			result["duration_ms"] = round((time.perf_counter() - case_started) * 1000, 2)
			results.append(result)

		list_status, session_list = client.request("GET", "/agents/sessions")
		listed_ids = {
			item.get("session_id")
			for item in session_list.get("sessions", [])
			if isinstance(item, dict)
		} if isinstance(session_list, dict) else set()
		results.append({
			"name": "session_is_listed_for_owner",
			"endpoint": "/agents/sessions",
			"status": "passed"
			if list_status == 200 and session_id in listed_ids
			else "failed",
			"status_code": list_status,
		})

		history_status, history = client.request(
			"GET", f"/agents/sessions/{session_id}"
		)
		messages = history.get("messages", []) if isinstance(history, dict) else []
		results.append({
			"name": "agent_turns_saved_to_chat",
			"endpoint": f"/agents/sessions/{session_id}",
			"status": "passed" if history_status == 200 and messages else "failed",
			"status_code": history_status,
			"message_count": len(messages),
		})
	finally:
		if not args.keep_session:
			delete_status, _ = client.request("DELETE", f"/agents/sessions/{session_id}")
			if delete_status != 200:
				results.append({
					"name": "evaluation_session_cleanup",
					"endpoint": f"/agents/sessions/{session_id}",
					"status": "failed",
					"status_code": delete_status,
				})

	passed = sum(result["status"] == "passed" for result in results)
	failed = sum(result["status"] == "failed" for result in results)
	skipped = sum(result["status"] == "skipped" for result in results)
	completed = passed + failed
	return {
		"started_at": datetime.now(timezone.utc).isoformat(),
		"base_url": args.base_url,
		"repository_id": args.repository_id,
		"session_id": session_id,
		"session_kept": args.keep_session,
		"summary": {
			"total": len(results),
			"passed": passed,
			"failed": failed,
			"skipped": skipped,
			"pass_rate": round(passed / completed, 4) if completed else 0.0,
			"duration_ms": round((time.perf_counter() - started) * 1000, 2),
		},
		"results": results,
	}


def main(argv: list[str] | None = None) -> int:
	args = _build_parser().parse_args(argv)
	try:
		report = run_evaluation(args)
	except (EvaluationError, OSError, json.JSONDecodeError) as error:
		print(f"Online evaluation could not run: {error}", file=sys.stderr)
		return 2

	serialized = json.dumps(report, indent=2, ensure_ascii=False)
	print(serialized)
	if args.output:
		args.output.parent.mkdir(parents=True, exist_ok=True)
		args.output.write_text(serialized + "\n", encoding="utf-8")
	return 1 if report["summary"]["failed"] else 0


if __name__ == "__main__":
	raise SystemExit(main())