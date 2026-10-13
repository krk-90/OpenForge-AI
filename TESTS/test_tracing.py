import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

project_root = str(Path(__file__).resolve().parents[1])
if project_root not in sys.path:
	sys.path.insert(0, project_root)

from APP.core.tracing import configure_langsmith_tracing, invoke_traced, trace_config


class LangSmithTracingTests(unittest.TestCase):
	def test_tracing_requires_explicit_opt_in_and_api_key(self):
		with patch.dict(os.environ, {"LANGSMITH_TRACING": "true", "LANGSMITH_API_KEY": "test-key"}, clear=True):
			self.assertTrue(configure_langsmith_tracing())
			self.assertEqual(os.environ["LANGSMITH_PROJECT"], "openforge-ai")
			self.assertEqual(os.environ["LANGCHAIN_TRACING_V2"], "true")

		with patch.dict(os.environ, {"LANGSMITH_TRACING": "true"}, clear=True):
			self.assertFalse(configure_langsmith_tracing())

	def test_trace_config_uses_openforge_service_metadata(self):
		config = trace_config("openforge.orchestrator", tags=["agent", "orchestrator"])

		self.assertEqual(config["run_name"], "openforge.orchestrator")
		self.assertEqual(config["tags"], ["openforge-ai", "agent", "orchestrator"])
		self.assertEqual(config["metadata"]["service"], "openforge-ai")
		self.assertNotIn("user_id", config["metadata"])


class TracedInvocationTests(unittest.IsolatedAsyncioTestCase):
	async def test_enabled_tracing_attaches_run_metadata(self):
		class FakeLLM:
			async def ainvoke(self, input_data, *, config=None):
				return SimpleNamespace(input=input_data, config=config)

		with patch.dict(os.environ, {"LANGSMITH_TRACING": "true", "LANGSMITH_API_KEY": "test-key"}):
			result = await invoke_traced(
				FakeLLM(), ["hello"], "openforge.test", tags=["test"],
			)

		self.assertEqual(result.config["run_name"], "openforge.test")
		self.assertEqual(result.config["tags"], ["openforge-ai", "test"])


if __name__ == "__main__":
	unittest.main()