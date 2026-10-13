import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from APP.core.security import get_supabase_client
from supabase import Client

router = APIRouter(prefix="/auth", tags=["auth"])
SupabaseDependency = Annotated[Client, Depends(get_supabase_client)]


class AuthCredentials(BaseModel):
	email: str = Field(min_length=3, max_length=320)
	password: str = Field(min_length=6, max_length=128)

	@field_validator("email")
	@classmethod
	def validate_email(cls, value: str) -> str:
		clean_email = value.strip()
		if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", clean_email):
			raise ValueError("Enter a valid email address")
		return clean_email


def _auth_result(response: Any, message: str) -> dict[str, Any]:
	user = getattr(response, "user", None)
	session = getattr(response, "session", None)
	return {
		"message": message,
		"user": {
			"id": str(user.id),
			"email": getattr(user, "email", None),
		} if user is not None else None,
		"session": {
			"access_token": session.access_token,
			"refresh_token": session.refresh_token,
			"token_type": session.token_type,
			"expires_in": session.expires_in,
		} if session is not None else None,
	}


@router.post("/signup", status_code=status.HTTP_201_CREATED)
def sign_up(
	credentials: AuthCredentials,
	supabase: SupabaseDependency,
) -> dict[str, Any]:
	try:
		response = supabase.auth.sign_up(
			{"email": credentials.email, "password": credentials.password}
		)
	except Exception as exc:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="Could not create the account. Check the email and password, then try again.",
		) from exc

	message = (
		"Account created. Check your email to confirm your address."
		if getattr(response, "session", None) is None
		else "Account created."
	)
	return _auth_result(response, message)


@router.post("/login")
def log_in(
	credentials: AuthCredentials,
	supabase: SupabaseDependency,
) -> dict[str, Any]:
	try:
		response = supabase.auth.sign_in_with_password(
			{"email": credentials.email, "password": credentials.password}
		)
	except Exception as exc:
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="Email or password is incorrect.",
		) from exc

	if getattr(response, "session", None) is None:
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="Supabase did not return a login session.",
		)
	return _auth_result(response, "You are signed in.")
