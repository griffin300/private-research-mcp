from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime

from app.search.official_sources import authority_search_variant

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
        distinctive = _distinctive_query_variant(compact)
        if distinctive:
            candidates.append(distinctive)
        authority_variant = authority_search_variant(compact)
        if authority_variant:
            candidates.append(authority_variant)
        if focused and focused.casefold() != compact.casefold():
            candidates.append(focused)
        candidates.append(f"{focused or compact} official documentation")
        candidates.extend(f"{topic} official documentation" for topic in topics[:1])
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
        if re.search(r"\b(?:paper|peer-reviewed|research|study|evidence)\b", compact, re.I):
            candidates.append(f"{focused or compact} research paper benchmark")
        if re.search(
            r"\b(?:bug|error|exception|failed|failure|issue|traceback|troubleshoot)\b",
            compact,
            re.I,
        ):
            candidates.append(f"{focused or compact} issue tracker discussion")
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


def _distinctive_query_variant(question: str) -> str | None:
    version = re.search(
        r"\b([A-Z][A-Za-z0-9+#.-]*)\s+(\d+\.\d+(?:\.\d+){0,2})\b", question
    )
    if version:
        phrase = f"{version.group(1)} {version.group(2)}"
        intent = "release date" if re.search(r"\b(?:date|release|released)\b", question, re.I) else "official documentation"
        return f'"{phrase}" {intent}'

    phrases = re.findall(
        r"\b(?:[A-Z]{2,10}|[A-Z][a-z]+)(?:\s+(?:[A-Z]{2,10}|[A-Z][a-z]+)){1,3}\b",
        question,
    )
    phrase_candidate = next(
        (
            value
            for value in phrases
            if any(token.isupper() and len(token) >= 2 for token in value.split())
            and value.split()[0].casefold()
            not in {"according", "how", "in", "on", "what", "when", "which"}
        ),
        None,
    )
    if not phrase_candidate:
        return None
    intent_tokens = [
        token
        for token in ("production", "transport", "release", "standard", "security")
        if re.search(rf"\b{token}\w*\b", question, re.I)
    ]
    return (
        f'"{phrase_candidate}" '
        f'{" ".join(intent_tokens[:3]) or "official documentation"}'
    )
