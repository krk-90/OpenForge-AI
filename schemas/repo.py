from pydantic import BaseModel


class RepositoryRecommendation(BaseModel):
    repository: str
    score: int
    stars: int
    language: str
    reason: str