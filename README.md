# OpenForge-AI
OpenForge is an AI-powered open source contribution mentor that helps developers discover, understand, and contribute to GitHub repositories. By combining GitHub intelligence, repository-aware RAG, and skill-based issue matching, OpenForge guides users from finding the right issue to submitting a successful pull request.


Repository
    │
    ▼
Repository Loader
    │
    ▼
Repository Cache
    │
    ▼
File Filter
(skip binaries, lock files,
generated code, dist, build)
    │
    ▼
Language Detector
    │
    ├─ Python
    ├─ TypeScript
    ├─ JavaScript
    ├─ Java
    └─ Go
    │
    ▼
AST Parser Layer
    │
    ├─ Functions
    ├─ Classes
    ├─ Interfaces
    ├─ Methods
    ├─ Imports
    └─ API Routes
    │
    ▼
Code Intelligence Layer
    │
    ├─ Function Map
    ├─ Class Map
    ├─ Dependency Map
    ├─ Call Graph
    ├─ Route Map
    └─ Config Map
    │
    ▼
Knowledge Graph Builder
    │
    ▼
Documentation Agent
    │
    ▼
RepositoryKnowledge
    │
    ├──────────────────┐
    │                  │
    ▼                  ▼
Summary Store     Metadata Store
    │                  │
    └────────┬─────────┘
             ▼
      Chunking Engine
             │
 ┌───────────┼───────────┐
 ▼           ▼           ▼
AST      Semantic     Hierarchical
Chunks    Chunks        Chunks
             │
             ▼
      Embedding Engine
             │
 ┌───────────┼───────────┐
 ▼           ▼           ▼
BM25      Vector DB   Graph DB
Index                  Index
             │
             ▼
        Query Router
             │
 ┌───────────┼────────────┬───────────┐
 ▼           ▼            ▼           ▼
Overview  Code Q&A   Architecture  Search
             │
             ▼
     Hybrid Retrieval
(BM25 + Dense + Graph)
             │
             ▼
         Reranker
             │
             ▼
   Context Compression
             │
             ▼
       RAG Reasoner
             │
             ▼
       Source Citer
             │
             ▼
       Final Answer