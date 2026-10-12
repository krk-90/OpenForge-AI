from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, HttpUrl, TypeAdapter, model_validator

class RepositoryRecommendation(BaseModel):
    repository: str
    score: int
    stars: int
    language: str
    reason: str
class RepositoryInput(BaseModel):
    repo_url: HttpUrl
    branch: str = "main"
    commit_sha: Optional[str] = None

    analysis_depth: Literal[
        "basic",
        "intermediate",
        "deep"
    ] = "deep"

    output_mode: Literal[
        "markdown",
        "json",
        "html"
    ] = "json"


class DocAgentRequest(BaseModel):
    repository: RepositoryInput

    explanation_type: Literal[
        "repository",
        "folder",
        "file",
        "class",
        "function"
    ]

    target_path: Optional[str] = None

    target_audience: Literal[
        "beginner",
        "intermediate",
        "expert"
    ] = "intermediate"

    max_words: int = Field(
        default=1500,
        ge=500,
        le=5000
    )

    include_diagrams: bool = True
    include_contributor_guide: bool = True
    include_improvements: bool = True    

    @model_validator(mode="after")
    def require_target_path_for_scoped_explanations(self):
        if self.explanation_type != "repository" and not self.target_path:
            raise ValueError("target_path is required for scoped explanations")
        return self

class FolderSummary(BaseModel):
    path: str
    purpose: str
    responsibilities: list[str]
    important_files: list[str]


class FileSummary(BaseModel):
    path: str
    purpose: str
    classes: list[str]
    functions: list[str]
    dependencies: list[str]
    summary: str


class ArchitectureFlow(BaseModel):
    name: str
    description: str
    flow_steps: list[str]


class ContributorGuide(BaseModel):
    difficulty: str
    starting_points: list[str]
    suggested_issues: list[str]


class RepositoryDocumentation(BaseModel):
    repository_name: str

    repository_summary: str = Field(min_length=501)

    architecture_overview: str

    tech_stack: list[str]

    main_modules: list[str] = Field(min_length=1)

    folders: list[FolderSummary] = Field(min_length=1)

    files: list[FileSummary]

    execution_flows: list[ArchitectureFlow] = Field(min_length=1)

    diagrams: list[str]

    contributor_guide: ContributorGuide

    improvement_suggestions: list[str]

    generated_word_count: int = Field(ge=0)

class DocumentationValidator:
    _adapter = TypeAdapter(RepositoryDocumentation)

    @classmethod
    def validate(
        cls,
        doc: str | bytes | dict[str, Any] | RepositoryDocumentation,
    ) -> RepositoryDocumentation:
        if isinstance(doc, (str, bytes, bytearray)):
            return cls._adapter.validate_json(doc)
        return cls._adapter.validate_python(doc)

class AgentState(BaseModel):

    repository_id: str

    repo_tree_generated: bool

    embeddings_created: bool

    documentation_generated: bool

    rag_index_created: bool

    knowledge_graph_created: bool

    errors: list[str]    

class RepositoryKnowledge(BaseModel):

    repository_name: str

    repo_summary: str

    tech_stack: list[str]

    architecture: str

    folders: dict

    files: dict

    classes: dict

    functions: dict

    dependencies: dict

    execution_flows: dict

    embeddings_id: str | None

    graph_id: str | None    