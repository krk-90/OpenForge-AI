import json
import os
import sys
from pathlib import Path

from langchain_core.messages import HumanMessage
from langchain_groq import ChatGroq
from pydantic import TypeAdapter

project_root = str(Path(__file__).resolve().parents[2])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from schemas.repo import RepositoryRecommendation
from DATABASE.supabase_db import save_repository_search

recommendations_adapter = TypeAdapter(list[RepositoryRecommendation])

class RepoDiscoveryAgent:

    def __init__(self, github_tools):

        self.tools = github_tools

        self.llm = ChatGroq(
            model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
            temperature=0
        )

    async def _search_repository(
        self,
        query: str,
        limit: int = 10
    ):
        
        search_tool = None

        for tool in self.tools:
            if tool.name == "search_repositories":
                search_tool = tool
                break

        if not search_tool:
            return []

        try:
            result = await search_tool.ainvoke(
                {
                    "query": query,
                    "perPage": limit
                }
            )

            if isinstance(result, str):
                result = json.loads(result)
            elif isinstance(result, list):
                text_content = next(
                    (
                        item.get("text")
                        for item in result
                        if isinstance(item, dict)
                        and item.get("type") == "text"
                    ),
                    None,
                )
                if text_content is not None:
                    result = json.loads(text_content)

            if isinstance(result, dict):
                repositories = result.get("items", [])
            else:
                repositories = result if isinstance(result, list) else []

        except Exception as e:
            print(e)
            return []

        try:
            save_repository_search(query, repositories)
        except Exception as e:
            print(f"Could not store repository search history in Supabase: {e}")
        return repositories

    async def retrieve_candidates(
        self,
        skills: list[str]
    ):
        repos = []

        for skill in skills:

            result = await self._search_repository(skill)

            if result:
                repos.extend(result)

        return repos

    def heuristic_score(
        self,
        repo: dict,
        skills: list[str]
    ):
        score = 0

        description = (
            repo.get("description", "") or ""
        ).lower()

        language = (
            repo.get("language", "") or ""
        ).lower()

        stars = repo.get("stargazers_count", 0)

        if language == "python":
            score += 40

        if stars > 1000:
            score += 20

        if stars > 10000:
            score += 10

        for skill in skills:

            if skill.lower() in description:
                score += 15

        if "agent" in description:
            score += 10

        if "rag" in description:
            score += 10

        if "llm" in description:
            score += 10

        return score

    async def rerank(
        self,
        repos,
        skills
    ) -> list[RepositoryRecommendation]:
        ranking_candidates = [
            {
                "repository": repo.get("full_name") or repo.get("name"),
                "description": (repo.get("description") or "")[:300],
                "language": repo.get("language"),
                "stars": repo.get("stargazers_count", 0),
                "open_issues": repo.get("open_issues_count", 0),
                "updated_at": repo.get("updated_at"),
                "local_score": repo.get("local_score", 0),
            }
            for repo in repos
        ]

        prompt = f"""
User Skills:

{skills}

Repositories:

{json.dumps(ranking_candidates, indent=2)}

Rank repositories.

Consider:
1. Contribution potential
2. Open source activity
3. Learning value
4. AI relevance
5. FastAPI/RAG/LangGraph fit

Return JSON:

[
 {{
   "repository":"",
   "score":0,
   "stars":0,
   "language":"",
   "reason":""
 }}
]
"""

        response = await self.llm.ainvoke(
            [HumanMessage(content=prompt)]
        )

        return recommendations_adapter.validate_json(response.content)

    async def discover(
        self,
        skills
    ):

        repositories = await self.retrieve_candidates(
            skills
        )

        scored = []

        seen = set()

        for repo in repositories:

            name = (
                repo.get("full_name")
                or repo.get("name")
            )

            if not name:
                continue

            if name in seen:
                continue

            seen.add(name)

            score = self.heuristic_score(
                repo,
                skills
            )

            repo["local_score"] = score

            scored.append(repo)

        scored.sort(
            key=lambda x: x["local_score"],
            reverse=True
        )

        top10 = scored[:10]

        return await self.rerank(
            top10,
            skills
        )