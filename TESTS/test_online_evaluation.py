import sys
import unittest
from pathlib import Path

project_root = str(Path(__file__).resolve().parents[1])
if project_root not in sys.path:
	sys.path.insert(0, project_root)

from Evalution.online import _substitute, evaluate_response


class OnlineEvaluationTests(unittest.TestCase):
	def test_dataset_placeholders_are_substituted_recursively(self):
		case = {
			"session_id": "{{session_id}}",
			"repository": {"url": "{{repository_url}}"},
			"items": ["{{repository_id}}"],
		}

		result = _substitute(case, {
			"session_id": "session-1",
			"repository_url": "https://github.com/acme/demo",
			"repository_id": "acme/demo",
		})

		self.assertEqual(result["session_id"], "session-1")
		self.assertEqual(result["repository"]["url"], "https://github.com/acme/demo")
		self.assertEqual(result["items"], ["acme/demo"])

	def test_contract_check_passes_required_fields_and_terms(self):
		case = {
			"name": "profile",
			"path": "/agents/profile",
			"checks": {
				"required_fields": ["profile", "discovery_terms"],
				"contains": {"discovery_terms": ["Python"]},
			},
		}

		result = evaluate_response(
			case,
			200,
			{"profile": {}, "discovery_terms": ["Python", "FastAPI"]},
		)

		self.assertEqual(result["status"], "passed")

	def test_contract_check_reports_missing_fields(self):
		case = {
			"name": "mentor",
			"path": "/agents/mentor",
			"checks": {"required_fields": ["first_task"]},
		}

		result = evaluate_response(case, 200, {"issue_summary": "Learn the code."})

		self.assertEqual(result["status"], "failed")
		self.assertIn("Missing field: first_task", result["checks"])

	def test_optional_mcp_unavailability_is_reported_as_skipped(self):
		case = {
			"name": "documentation",
			"path": "/agents/documentation",
			"skip_statuses": [503],
		}

		result = evaluate_response(case, 503, {"detail": "MCP unavailable"})

		self.assertEqual(result["status"], "skipped")


if __name__ == "__main__":
	unittest.main()