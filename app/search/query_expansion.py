from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

_STOP = {
    "a",
    "an",
    "and",
    "according",
    "are",
    "does",
    "differ",
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
    "was",
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
        current_year = datetime.now(UTC).year
        time_sensitive = bool(
            re.search(r"\b(latest|current|today|recent|price|as of|right now)\b", compact, re.I)
            or re.search(rf"\b{current_year}\b", compact)
        )
        focused = " ".join(entities[:12])
        candidates = [compact]
        if focused and focused.casefold() != compact.casefold():
            candidates.append(focused)
        candidates.append(f"{focused or compact} official documentation")
        candidates.extend(f"{topic} official documentation" for topic in topics[:2])
        if re.search(r"\b(error|exception|failed|traceback|code\s+\d+)\b", compact, re.I):
            candidates.append(f'"{compact}" issue tracker')
        if re.search(r"\b(compare|versus|vs\.?|difference|better)\b", compact, re.I):
            candidates.extend(f"{topic} specification benchmark" for topic in topics[:2])
        if time_sensitive:
            candidates.append(f"{focused or compact} current release notes {current_year}")
        elif re.search(r"\b(?:release|released)\b", compact, re.I) and re.search(
            r"\b\d+\.\d+(?:\.\d+)?\b", compact
        ):
            candidates.append(f"{focused or compact} official release page")
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
