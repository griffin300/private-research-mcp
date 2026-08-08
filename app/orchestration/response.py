from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any, Literal
from urllib.parse import urlsplit

from app.models import ResearchPackage, SearchSnippetRecord, SourceRecord
from app.ranking.lexical import meaningful_tokens

ResponseDetail = Literal["compact", "full"]

_WHITESPACE = re.compile(r"\s+")
_MIN_CONTEXT_CHARS = 4_000
_MAX_CONTEXT_CHARS = 50_000


def research_response(
    package: ResearchPackage,
    *,
    detail: ResponseDetail = "compact",
    max_chars: int = 14_000,
) -> dict[str, Any]:
    """Present a research package without exposing internal ranking/debug bulk by default."""
    if detail == "full":
        return package.model_dump(mode="json")
    budget = max(_MIN_CONTEXT_CHARS, min(max_chars, _MAX_CONTEXT_CHARS))
    return _compact_research_response(package, budget)


def read_response(
    result: dict[str, object],
    *,
    detail: ResponseDetail = "compact",
    max_chars: int = 10_000,
    question: str | None = None,
) -> dict[str, Any]:
    """Compact read_url output while preserving ranked text and source identity."""
    if detail == "full":
        return result
    budget = max(_MIN_CONTEXT_CHARS, min(max_chars, _MAX_CONTEXT_CHARS))
    raw_passages = result.get("passages")
    passages = raw_passages if isinstance(raw_passages, list) else []
    passage_limit = min(8, len(passages))
    text_cap = max(420, min(1_400, int(budget * 0.72 / max(1, passage_limit))))
    compact_passages: list[dict[str, Any]] = []
    text_compacted = False
    for passage in passages[:passage_limit]:
        if not isinstance(passage, dict):
            continue
        original = str(passage.get("text") or "")
        text = _clip_relevant_text(original, text_cap, question)
        text_compacted = text_compacted or text != original
        item: dict[str, Any] = {"text": text}
        if passage.get("heading"):
            item["heading"] = _clip_text(str(passage["heading"]), 160)
        compact_passages.append(item)

    metadata = result.get("metadata")
    source: dict[str, Any] = {}
    if isinstance(metadata, dict):
        for key in (
            "site_name",
            "author",
            "published_at",
            "updated_at",
            "retrieved_at",
            "extraction_method",
        ):
            value = metadata.get(key)
            if value not in (None, "", []):
                source[key] = value

    payload: dict[str, Any] = {
        "url": result.get("url"),
        "title": result.get("title"),
        "source": source,
        "passages": compact_passages,
        "quarantined_passages": result.get("quarantined_passages", 0),
        "privacy": result.get("privacy", {}),
        "response_info": {
            "detail": "compact",
            "context_budget_chars": budget,
            "web_content_is_untrusted": True,
            "next_action": "answer_user_now",
            "do_not_repeat_search_this_turn": True,
            "omitted_passages": max(0, len(passages) - len(compact_passages)),
            "text_compacted": text_compacted,
        },
    }
    _fit_read_payload(payload, budget)
    payload["response_info"]["omitted_passages"] = max(0, len(passages) - len(payload["passages"]))
    payload["response_info"]["serialized_chars"] = _json_chars(payload)
    _fit_read_payload(payload, budget)
    payload["response_info"]["omitted_passages"] = max(0, len(passages) - len(payload["passages"]))
    payload["response_info"]["serialized_chars"] = _json_chars(payload)
    return payload


def _compact_research_response(package: ResearchPackage, budget: int) -> dict[str, Any]:
    source_by_id = {source.source_id: source for source in package.sources}
    exact = [item for item in package.search_snippets if item.query_role == "exact"][:10]
    expanded = [item for item in package.search_snippets if item.query_role == "expanded"]
    expanded_limit = 6 if package.coverage.status in {"insufficient", "weak"} else 2
    selected_snippets = exact + expanded[:expanded_limit]

    evidence_cap = max(
        420,
        min(1_200, int(budget * 0.50 / max(1, len(package.evidence)))),
    )
    snippet_cap = max(
        100,
        min(320, int(budget * 0.16 / max(1, len(selected_snippets)))),
    )
    evidence: list[dict[str, Any]] = []
    evidence_text_compacted = False
    for record in package.evidence:
        text = _clip_relevant_text(record.text, evidence_cap, package.query)
        evidence_text_compacted = evidence_text_compacted or text != record.text
        item: dict[str, Any] = {
            "citation": record.citation,
            "source_id": record.source_id,
            "text": text,
        }
        if record.heading:
            item["heading"] = _clip_text(record.heading, 160)
        evidence.append(item)

    strong_verified_context = (
        package.coverage.status in {"moderate", "strong"}
        and not package.coverage.missing_topics
        and len(evidence) >= 4
    )
    evidence_urls = {
        _url_identity(source_by_id[str(item["source_id"])].url)
        for item in evidence
        if str(item["source_id"]) in source_by_id
    }
    answer_topics = [
        *package.coverage.covered_topics,
        *package.coverage.missing_topics,
    ]
    essential_snippets = _essential_snippet_indexes(
        selected_snippets,
        answer_topics or [package.query],
    )
    snippets: list[dict[str, Any]] = []
    exact_position = 0
    for snippet_index, snippet_record in enumerate(selected_snippets):
        item_cap = snippet_cap
        verified_duplicate = (
            strong_verified_context
            and _url_identity(snippet_record.url) in evidence_urls
        )
        if snippet_record.query_role == "exact":
            exact_position += 1
            if verified_duplicate:
                # Preserve the exact result identity and citation while extracted
                # evidence from the same page carries the answer-bearing text.
                item_cap = 0
            elif snippet_index in essential_snippets:
                item_cap = max(item_cap, 180)
            elif strong_verified_context and exact_position > 2:
                # Keep all exact result identities for citation safety, but spend
                # snippet text on query-distinct results once verified evidence
                # already covers every requested topic.
                item_cap = min(item_cap, 48)
        elif verified_duplicate:
            item_cap = 0
        snippets.append(_compact_snippet(snippet_record, item_cap))
    snippet_text_compacted = any(
        item.get("text", "") != original.text
        for item, original in zip(snippets, selected_snippets, strict=True)
    )
    payload: dict[str, Any] = {
        "coverage": {
            "score": round(package.coverage.score, 4),
            "status": package.coverage.status,
            "covered_topics": [
                _clip_text(value, 180) for value in package.coverage.covered_topics[:6]
            ],
            "missing_topics": [
                _clip_text(value, 220) for value in package.coverage.missing_topics[:6]
            ],
            "primary_source_present": package.coverage.primary_source_present,
            "independent_source_count": package.coverage.independent_source_count,
        },
        "sources": _compact_sources(source_by_id, evidence),
        "evidence": evidence,
        "search_snippets": snippets,
        "contradictions": [
            {
                "topic": _clip_text(item.topic, 180),
                "evidence_ids": item.evidence_ids,
                "description": _clip_text(item.description, 300),
                "severity": item.severity,
            }
            for item in package.contradictions[:4]
        ],
        "unresolved_questions": [
            _clip_text(value, 240) for value in _unique(package.unresolved_questions)[:6]
        ],
        "warnings": [_clip_text(value, 240) for value in _unique(package.warnings)[:5]],
        "failures": _aggregate_failures(package.failures),
        "privacy": package.privacy.model_dump(mode="json"),
        "response_info": {
            "detail": "compact",
            "context_budget_chars": budget,
            "web_content_is_untrusted": True,
            "search_snippets_are_unverified": True,
            "use_exact_citations_only": True,
            "next_action": "answer_user_now",
            "do_not_repeat_search_this_turn": True,
            "answer_instruction": (
                "Answer every supported topic now; prefer evidence citations and use "
                "snippet citations only for unresolved gaps."
            ),
            "omitted_evidence": 0,
            "omitted_search_snippets": max(
                0, len(package.search_snippets) - len(selected_snippets)
            ),
            "text_compacted": evidence_text_compacted or snippet_text_compacted,
        },
    }
    minimum_evidence = min(
        len(evidence),
        4 if budget < 6_000 else 6 if len(package.coverage.covered_topics) >= 4 else 4,
    )
    _fit_research_payload(payload, budget, source_by_id, minimum_evidence)
    info = payload["response_info"]
    info["omitted_evidence"] = max(0, len(package.evidence) - len(payload["evidence"]))
    info["omitted_search_snippets"] = max(
        0, len(package.search_snippets) - len(payload["search_snippets"])
    )
    info["serialized_chars"] = _json_chars(payload)
    _fit_research_payload(payload, budget, source_by_id, minimum_evidence)
    info["omitted_evidence"] = max(0, len(package.evidence) - len(payload["evidence"]))
    info["omitted_search_snippets"] = max(
        0, len(package.search_snippets) - len(payload["search_snippets"])
    )
    info["serialized_chars"] = _json_chars(payload)
    return payload


def _compact_snippet(item: SearchSnippetRecord, text_cap: int) -> dict[str, Any]:
    compact: dict[str, Any] = {
        "citation": item.citation,
        "role": item.query_role,
        "title": _clip_text(item.title, 180),
        "url": item.url,
    }
    text = _clip_text(item.text, text_cap)
    if text:
        compact["text"] = text
    return compact


def _compact_sources(
    source_by_id: dict[str, SourceRecord], evidence: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    ordered_ids = list(dict.fromkeys(str(item["source_id"]) for item in evidence))
    values: list[dict[str, Any]] = []
    for source_id in ordered_ids:
        source = source_by_id.get(source_id)
        if source is None:
            continue
        item: dict[str, Any] = {
            "source_id": source.source_id,
            "title": _clip_text(source.title, 180),
            "url": source.url,
        }
        if source.published_at is not None:
            item["published_at"] = source.published_at.isoformat()
        if source.source_type:
            item["source_type"] = source.source_type
        values.append(item)
    return values


def _aggregate_failures(failures: list[dict[str, str]]) -> list[dict[str, Any]]:
    counts = Counter(
        (str(item.get("stage", "unknown")), str(item.get("error", "unknown"))) for item in failures
    )
    return [
        {
            "stage": _clip_text(stage, 100),
            "error": _clip_text(error, 180),
            "count": count,
        }
        for (stage, error), count in counts.most_common(6)
    ]


def _fit_research_payload(
    payload: dict[str, Any],
    budget: int,
    source_by_id: dict[str, SourceRecord],
    minimum_evidence: int,
) -> None:
    evidence_floor = 180 if budget < 6_000 else 300
    snippet_floor = 40 if budget < 6_000 else 80
    while _json_chars(payload) > budget:
        snippets = payload["search_snippets"]
        expanded_indexes = [
            index for index, item in enumerate(snippets) if item.get("role") == "expanded"
        ]
        if expanded_indexes:
            snippets.pop(expanded_indexes[-1])
            continue
        warnings = payload["warnings"]
        if len(warnings) > 2:
            warnings.pop()
            continue
        unresolved = payload["unresolved_questions"]
        if len(unresolved) > 3:
            unresolved.pop()
            continue
        covered_topics = payload["coverage"]["covered_topics"]
        if len(covered_topics) > 2:
            covered_topics.pop()
            continue
        evidence = payload["evidence"]
        longest_evidence = _longest_text_item(evidence, floor=evidence_floor)
        if longest_evidence is not None:
            _shrink_item(longest_evidence, floor=evidence_floor, step=140)
            payload["response_info"]["text_compacted"] = True
            continue
        longest_snippet = _longest_text_item(snippets, floor=snippet_floor)
        if longest_snippet is not None:
            _shrink_item(longest_snippet, floor=snippet_floor, step=60)
            payload["response_info"]["text_compacted"] = True
            continue
        if len(evidence) > minimum_evidence:
            evidence.pop()
            payload["sources"] = _compact_sources(source_by_id, evidence)
            continue
        contradictions = payload["contradictions"]
        if contradictions:
            contradictions.pop()
            continue
        failures = payload["failures"]
        if len(failures) > 1:
            failures.pop()
            continue
        source_metadata_removed = False
        for source in reversed(payload["sources"]):
            for field in ("published_at", "source_type"):
                if field in source:
                    source.pop(field)
                    source_metadata_removed = True
                    break
            if source_metadata_removed:
                break
        if source_metadata_removed:
            continue
        query = str(payload.get("query") or "")
        if len(query) > 240:
            payload["query"] = _clip_text(query, max(240, len(query) - 120))
            continue
        if _shrink_longest_field(payload["sources"], "title", floor=60, step=60):
            continue
        if _shrink_longest_field(snippets, "title", floor=60, step=60):
            continue
        if _shrink_longest_field(evidence, "heading", floor=40, step=40):
            continue
        if warnings:
            warnings.pop()
            continue
        if unresolved:
            unresolved.pop()
            continue
        if contradictions:
            contradictions.pop()
            continue
        if failures:
            failures.pop()
            continue
        missing_topics = payload["coverage"]["missing_topics"]
        if len(missing_topics) > 1:
            missing_topics.pop()
            continue
        if covered_topics:
            covered_topics.pop()
            continue
        longest_evidence = _longest_text_item(evidence, floor=100)
        if longest_evidence is not None:
            _shrink_item(longest_evidence, floor=100, step=80)
            payload["response_info"]["text_compacted"] = True
            continue
        longest_snippet = _longest_text_item(snippets, floor=20)
        if longest_snippet is not None:
            _shrink_item(longest_snippet, floor=20, step=40)
            payload["response_info"]["text_compacted"] = True
            continue
        if len(evidence) > 2:
            evidence.pop()
            payload["sources"] = _compact_sources(source_by_id, evidence)
            continue
        # Pathological exact URLs can alone exceed a caller-supplied budget. Keep
        # every citation target intact and explicitly report the rare excess.
        payload["response_info"]["budget_exceeded_for_exact_urls"] = True
        break


def _fit_read_payload(payload: dict[str, Any], budget: int) -> None:
    while _json_chars(payload) > budget:
        passages = payload["passages"]
        longest = _longest_text_item(passages, floor=320)
        if longest is not None:
            _shrink_item(longest, floor=320, step=160)
            payload["response_info"]["text_compacted"] = True
            continue
        if len(passages) > 3:
            passages.pop()
            continue
        payload["response_info"]["budget_exceeded_for_exact_url"] = True
        break
    payload["response_info"]["omitted_passages"] = max(
        payload["response_info"]["omitted_passages"], 0
    )


def _longest_text_item(items: list[dict[str, Any]], *, floor: int) -> dict[str, Any] | None:
    eligible = [item for item in items if len(str(item.get("text") or "")) > floor]
    return max(eligible, key=lambda item: len(str(item.get("text") or "")), default=None)


def _shrink_item(item: dict[str, Any], *, floor: int, step: int) -> None:
    text = str(item.get("text") or "")
    item["text"] = _clip_text(text, max(floor, len(text) - step))


def _shrink_longest_field(
    items: list[dict[str, Any]], field: str, *, floor: int, step: int
) -> bool:
    eligible = [item for item in items if len(str(item.get(field) or "")) > floor]
    if not eligible:
        return False
    item = max(eligible, key=lambda value: len(str(value.get(field) or "")))
    text = str(item[field])
    item[field] = _clip_text(text, max(floor, len(text) - step))
    return True


def _clip_text(value: str, limit: int) -> str:
    text = _WHITESPACE.sub(" ", value).strip()
    if len(text) <= limit:
        return text
    if limit <= 1:
        return "…"[:limit]
    candidate = text[: limit - 1].rstrip()
    sentence_end = max(candidate.rfind(". "), candidate.rfind("? "), candidate.rfind("! "))
    if sentence_end >= max(80, limit // 2):
        candidate = candidate[: sentence_end + 1]
    else:
        word_end = candidate.rfind(" ")
        if word_end >= max(40, limit // 2):
            candidate = candidate[:word_end]
    return candidate.rstrip() + "…"


def _clip_relevant_text(value: str, limit: int, query: str | None) -> str:
    text = _WHITESPACE.sub(" ", value).strip()
    if len(text) <= limit or not query:
        return _clip_text(text, limit)
    terms = set(meaningful_tokens(query))
    if not terms:
        return _clip_text(text, limit)
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", text)
        if sentence.strip()
    ]
    matched: list[tuple[int, str, set[str], int]] = []
    for index, sentence in enumerate(sentences):
        sentence_terms = set(meaningful_tokens(sentence))
        overlap = terms & sentence_terms
        if overlap:
            occurrences = sum(sentence.casefold().count(term.casefold()) for term in terms)
            matched.append((index, sentence, overlap, occurrences))

    # Extract several complete, non-adjacent answer-bearing sentences when a
    # question has multiple facets. One lexical window can otherwise discard a
    # second fact even though the full evidence record contains it.
    selected: list[tuple[int, str]] = []
    covered: set[str] = set()
    remaining = list(matched)
    while remaining and len(selected) < 4:
        best = max(
            remaining,
            key=lambda item: (
                12 * len(item[2] - covered) + 4 * len(item[2]) + item[3],
                -item[0],
            ),
        )
        remaining.remove(best)
        proposed = sorted([*selected, (best[0], best[1])])
        proposed_text = " … ".join(sentence for _, sentence in proposed)
        proposed_prefix = "…" if proposed[0][0] > 0 else ""
        proposed_suffix = "…" if proposed[-1][0] < len(sentences) - 1 else ""
        if len(proposed_prefix + proposed_text + proposed_suffix) > limit:
            if not selected:
                return _clip_relevant_window(text, limit, terms)
            continue
        selected = proposed
        covered.update(best[2])

    if selected:
        rendered = " … ".join(sentence for _, sentence in selected)
        prefix = "…" if selected[0][0] > 0 else ""
        suffix = "…" if selected[-1][0] < len(sentences) - 1 else ""
        return prefix + rendered + suffix
    return _clip_relevant_window(text, limit, terms)


def _clip_relevant_window(text: str, limit: int, terms: set[str]) -> str:
    lowered = text.casefold()
    centers = [
        match.start()
        for term in terms
        for match in re.finditer(re.escape(term.casefold()), lowered)
    ]
    if not centers:
        return _clip_text(text, limit)
    window_size = max(1, limit - 2)
    candidates: list[tuple[int, int, int]] = []
    for center in centers:
        start = max(0, min(center - window_size // 3, len(text) - window_size))
        end = min(len(text), start + window_size)
        window = lowered[start:end]
        distinct = sum(term.casefold() in window for term in terms)
        occurrences = sum(window.count(term.casefold()) for term in terms)
        candidates.append((distinct * 10 + occurrences, -start, start))
    _, _, start = max(candidates)
    end = min(len(text), start + window_size)
    if start > 0:
        next_space = text.find(" ", start)
        if 0 <= next_space < end - 40:
            start = next_space + 1
    if end < len(text):
        previous_space = text.rfind(" ", start + 40, end)
        if previous_space > start:
            end = previous_space
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return prefix + text[start:end].strip() + suffix


def _essential_snippet_indexes(
    snippets: list[SearchSnippetRecord], topics: list[str]
) -> set[int]:
    essential = set(range(min(2, len(snippets))))
    for topic in topics[:6]:
        terms = set(meaningful_tokens(topic))
        if not terms:
            continue
        scored: list[tuple[float, int]] = []
        for index, snippet in enumerate(snippets):
            text_terms = set(meaningful_tokens(f"{snippet.title} {snippet.text}"))
            coverage = len(terms & text_terms) / len(terms)
            if coverage > 0:
                scored.append((coverage + 0.10 * snippet.relevance_score, index))
        if scored:
            essential.add(max(scored, key=lambda item: (item[0], -item[1]))[1])
        if len(essential) >= 6:
            break
    return essential


def _url_identity(value: str) -> tuple[str, str, int | None, str, str]:
    parsed = urlsplit(value)
    return (
        parsed.scheme.casefold(),
        (parsed.hostname or "").casefold().rstrip("."),
        parsed.port,
        parsed.path.rstrip("/") or "/",
        parsed.query,
    )


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _json_chars(value: dict[str, Any]) -> int:
    return len(json.dumps(value, ensure_ascii=False))
