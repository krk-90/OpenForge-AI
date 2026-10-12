import sys
import unittest
from pathlib import Path

project_root = str(Path(__file__).resolve().parents[1])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from Agents.profile.profile_agent import DeveloperProfile, ProfileAgent


class ProfileAgentTests(unittest.TestCase):
    def setUp(self):
        self.agent = ProfileAgent()

    def test_normalizes_comma_separated_profile_terms(self):
        profile = self.agent.build_profile({
            "skills": " Python, FastAPI, , python ",
            "interests": "open source, developer tools",
        })

        self.assertEqual(profile.skills, ["Python", "FastAPI"])
        self.assertEqual(profile.interests, ["open source", "developer tools"])

    def test_discovery_terms_merge_fields_without_duplicates(self):
        profile = DeveloperProfile.model_validate({
            "skills": ["Python", "FastAPI"],
            "interests": ["fastapi", "open source"],
            "preferred_languages": "Python, TypeScript",
            "contribution_goals": ["Improve documentation"],
        })

        self.assertEqual(
            self.agent.discovery_terms(profile),
            ["Python", "FastAPI", "open source", "TypeScript"],
        )

    def test_rejects_non_string_profile_terms(self):
        with self.assertRaisesRegex(ValueError, "Each profile term must be a string"):
            DeveloperProfile.model_validate({"skills": ["Python", 5]})


if __name__ == "__main__":
    unittest.main()