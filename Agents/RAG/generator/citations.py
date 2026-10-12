from __future__ import annotations

import re

from Agents.RAG.retriever.retrieval import RetrievedChunk


_CITATION_PATTERN = re.compile(r"[\[【]([^\]】]+)[\]】]")


class SourceCiter:
    def cite(self, answer: str, chunks: list[RetrievedChunk]) -> str:
        sources = list(dict.fromkeys(chunk.source for chunk in chunks if chunk.source))
        known = {source.casefold(): source for source in sources}
        cited: set[str] = set()

        def normalize(match: re.Match) -> str:
            candidate = match.group(1).strip()
            source = known.get(candidate.casefold())
            if source is None:
                return match.group(0)
            cited.add(source)
            return f"[{source}]"

        normalized = _CITATION_PATTERN.sub(normalize, answer.strip())
        if not cited and sources:
            normalized = f"{normalized}\n\nSources: " + ", ".join(
                f"[{source}]" for source in sources[:5]
            )
        return normalized


__all__ = ["SourceCiter"]