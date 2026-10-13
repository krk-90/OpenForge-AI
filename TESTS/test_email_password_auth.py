import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

project_root = str(Path(__file__).resolve().parents[1])
if project_root not in sys.path:
	sys.path.insert(0, project_root)

from fastapi.testclient import TestClient

from APP.core.security import get_supabase_client
from APP.main import app


class FakeAuth:
	def __init__(self):
		self.signup_credentials = None
		self.login_credentials = None

	def sign_up(self, credentials):
		self.signup_credentials = credentials
		return SimpleNamespace(
			user=SimpleNamespace(id="user-123", email=credentials["email"]),
			session=None,
		)

	def sign_in_with_password(self, credentials):
		self.login_credentials = credentials
		return SimpleNamespace(
			user=SimpleNamespace(id="user-123", email=credentials["email"]),
			session=SimpleNamespace(
				access_token="access-token",
				refresh_token="refresh-token",
				token_type="bearer",
				expires_in=3600,
			),
		)


class EmailPasswordAuthTests(unittest.TestCase):
	def setUp(self):
		self.auth = FakeAuth()
		app.dependency_overrides.clear()
		app.dependency_overrides[get_supabase_client] = lambda: SimpleNamespace(auth=self.auth)
		self.addCleanup(app.dependency_overrides.clear)
		self.client = TestClient(app)

	def test_signup_accepts_email_and_password(self):
		response = self.client.post(
			"/auth/signup",
			json={"email": " person@example.com ", "password": "secret123"},
		)
		self.assertEqual(response.status_code, 201)
		self.assertEqual(
			self.auth.signup_credentials,
			{"email": "person@example.com", "password": "secret123"},
		)
		self.assertIn("Check your email", response.json()["message"])

	def test_login_returns_session_tokens(self):
		response = self.client.post(
			"/auth/login",
			json={"email": "person@example.com", "password": "secret123"},
		)
		self.assertEqual(response.status_code, 200)
		self.assertEqual(self.auth.login_credentials["email"], "person@example.com")
		self.assertEqual(response.json()["session"]["access_token"], "access-token")
		self.assertEqual(response.json()["user"]["id"], "user-123")

	def test_rejects_invalid_email(self):
		response = self.client.post(
			"/auth/signup",
			json={"email": "not-an-email", "password": "secret123"},
		)
		self.assertEqual(response.status_code, 422)
		self.assertIsNone(self.auth.signup_credentials)

	def test_root_serves_login_and_signup_form(self):
		response = self.client.get("/")
		self.assertEqual(response.status_code, 200)
		self.assertIn("/auth/signup", response.text)
		self.assertIn("/auth/login", response.text)


if __name__ == "__main__":
	unittest.main()