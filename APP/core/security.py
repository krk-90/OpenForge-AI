import os

from dotenv import load_dotenv
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase import Client, create_client

load_dotenv()

bearer_scheme = HTTPBearer(auto_error=False)


def get_supabase_client() -> Client:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")

    if not url or not key:
        raise HTTPException(
            status_code=500,
            detail="SUPABASE_URL or SUPABASE_KEY is missing.",
        )

    return create_client(url, key)


def require_auth_credentials(
    credentials: HTTPAuthorizationCredentials | None,
) -> HTTPAuthorizationCredentials:
    if not credentials:
        raise HTTPException(status_code=401, detail="Bearer token required")
    return credentials


def get_authenticated_user_id(
    credentials: HTTPAuthorizationCredentials | None,
) -> str:
    auth = require_auth_credentials(credentials)

    try:
        supabase = get_supabase_client()
        user = supabase.auth.get_user(auth.credentials)
        if user is None or getattr(user, "user", None) is None:
            raise ValueError("User not found")
        return str(user.user.id)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
