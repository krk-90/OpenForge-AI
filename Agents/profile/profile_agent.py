from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


def normalize_profile_terms(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        terms = value.split(",")
    elif isinstance(value, (list, tuple, set)):
        terms = value
    else:
        raise ValueError("Profile terms must be a string or a sequence of strings")

    normalized = []
    seen = set()
    for term in terms:
        if not isinstance(term, str):
            raise ValueError("Each profile term must be a string")
        clean_term = term.strip()
        key = clean_term.casefold()
        if clean_term and key not in seen:
            normalized.append(clean_term)
            seen.add(key)
    return normalized


class DeveloperProfile(BaseModel):
    display_name: str = ""
    github_username: str = ""
    bio: str = ""
    skills: list[str] = Field(default_factory=list)
    interests: list[str] = Field(default_factory=list)
    preferred_languages: list[str] = Field(default_factory=list)
    experience_level: Literal["beginner", "intermediate", "advanced"] = "beginner"
    contribution_goals: list[str] = Field(default_factory=list)

    @field_validator(
        "skills",
        "interests",
        "preferred_languages",
        "contribution_goals",
        mode="before",
    )
    @classmethod
    def normalize_terms(cls, value: Any) -> list[str]:
        return normalize_profile_terms(value)


class ProfileAgent:
    def build_profile(self, profile_data: dict[str, Any] | DeveloperProfile) -> DeveloperProfile:
        if isinstance(profile_data, DeveloperProfile):
            return profile_data
        return DeveloperProfile.model_validate(profile_data)

    @staticmethod
    def discovery_terms(profile: DeveloperProfile) -> list[str]:
        return normalize_profile_terms(
            profile.skills + profile.interests + profile.preferred_languages
        )