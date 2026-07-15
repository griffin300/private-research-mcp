from __future__ import annotations

import re
from dataclasses import dataclass

_STOP = {
    "a",
    "an",
    "and",
    "are",
    "for",
    "from",
    "how",
    "in",
    "is",
    "of",
    "on",
    "or",
    "the",
    "to",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
}
_ABBREVIATIONS = {
    "ssrf": "server side request forgery",
    "mcp": "model context protocol",
    "llm": "large language model",
    "dns": "domain name system",
    "api": "application programming interface",
}


@dataclass(frozen=True, slots=True)
class QueryPlan:
    original: str
    queries: list[str]
    topics: list[str]
    time_sensitive: bool


class HeuristicQueryPlanner:
    def plan(self, question: str, limit: int) -> QueryPlan:
        compact = " ".join(question.split()).strip()
        tokens = re.findall(r"[A-Za-z0-9_.+#-]+", compact)
        entities = [t for t in tokens if t.lower() not in _STOP and len(t) > 2]
        topics = self._topics(compact, entities)
        time_sensitive = bool(
            re.search(
                r"\b(latest|current|today|recent|version|release|price|202[4-9])\b", compact, re.I
            )
        )
        candidates = [compact]
        candidates.extend(f"{topic} official documentation" for topic in topics[:3])
        if re.search(r"\b(error|exception|failed|traceback|code\s+\d+)\b", compact, re.I):
            candidates.append(f'"{compact}" issue tracker')
        if re.search(r"\b(compare|versus|vs\.?|difference|better)\b", compact, re.I):
            candidates.extend(f"{topic} specification benchmark" for topic in topics[:2])
        if time_sensitive:
            candidates.append(f"{compact} release notes 2026")
        expanded = [
            f"{compact} {_ABBREVIATIONS[t.lower()]}"
            for t in entities
            if t.lower() in _ABBREVIATIONS
        ]
        candidates.extend(expanded)
        candidates.extend(f"{compact} {kind}" for kind in ("paper", "issue", "forum"))
        unique: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            key = candidate.casefold()
            if key not in seen:
                seen.add(key)
                unique.append(candidate[:500])
            if len(unique) >= limit:
                break
        return QueryPlan(compact, unique, topics, time_sensitive)

    @staticmethod
    def _topics(question: str, entities: list[str]) -> list[str]:
        parts = re.split(r"[;?]|\b(?:and|versus|vs\.)\b", question, flags=re.I)
        topics = [" ".join(part.split()) for part in parts if len(part.split()) >= 2]
        if not topics and entities:
            topics = [" ".join(entities[:6])]
        return topics[:8]
