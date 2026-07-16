from __future__ import annotations

import json
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


def split_compound_query(question: str, limit: int = 4) -> list[str]:
    """Split only explicit machine-style query batches, not normal prose questions."""
    compact = " ".join(question.split()).strip()
    if not compact:
        return [compact]

    structured = _structured_queries(question)
    if structured:
        return _valid_query_parts(structured, compact, limit)

    raw_lines = [line for line in question.splitlines() if line.strip()]
    lines = [re.sub(r"^\s*(?:[-*•]|\d{1,2}[.)])\s*", "", line).strip() for line in raw_lines]
    marked_lines = all(re.match(r"^\s*(?:[-*•]|\d{1,2}[.)])\s+", line) for line in raw_lines)
    if marked_lines and len(lines) >= 2 and all(_looks_like_query_part(part) for part in lines):
        return _valid_query_parts(lines, compact, limit)

    labeled = re.split(r"\s+(?=(?:query|search)\s+\d{1,2}\s*[:.)-])", compact, flags=re.I)
    labeled = [
        re.sub(r"^(?:query|search)\s+\d{1,2}\s*[:.)-]\s*", "", part, flags=re.I) for part in labeled
    ]
    if len(labeled) >= 2 and all(_looks_like_query_part(part) for part in labeled):
        return _valid_query_parts(labeled, compact, limit)

    questions = [f"{part.strip()}?" for part in compact.split("?") if part.strip()]
    if len(questions) >= 2 and all(_looks_like_query_part(part) for part in questions):
        return _valid_query_parts(questions, compact, limit)

    for separator in (r"\s*;\s*", r"\s+\|\s+", r"\s+(?:OR|\|\|)\s+"):
        parts = [part.strip() for part in re.split(separator, compact) if part.strip()]
        if len(parts) >= 2 and all(_looks_like_query_part(part) for part in parts):
            return _valid_query_parts(parts, compact, limit)
    return [compact]


def _structured_queries(question: str) -> list[str]:
    stripped = question.strip()
    if not stripped or stripped[0] not in "[{":
        return []
    try:
        parsed = json.loads(stripped)
    except (json.JSONDecodeError, TypeError):
        return []
    values = parsed.get("queries") if isinstance(parsed, dict) else parsed
    if not isinstance(values, list):
        return []
    return [value for value in values if isinstance(value, str)]


def _valid_query_parts(parts: list[str], fallback: str, limit: int) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    bounded_limit = max(1, limit)
    for part in parts:
        compact = re.sub(r"^[;|,\s]+", "", " ".join(part.split()).strip())[:500]
        key = compact.casefold()
        if compact and key not in seen:
            seen.add(key)
            unique.append(compact)
        if len(unique) >= bounded_limit:
            break
    return unique if len(unique) >= 2 else [fallback]


def _looks_like_query_part(value: str) -> bool:
    return len(re.findall(r"[A-Za-z0-9_.+#-]+", value)) >= 3


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
