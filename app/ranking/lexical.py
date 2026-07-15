from __future__ import annotations

import math
import re
from collections import Counter
from itertools import pairwise

from app.models import Passage

_STOP = {
    "a",
    "according",
    "an",
    "and",
    "are",
    "did",
    "do",
    "does",
    "for",
    "from",
    "how",
    "in",
    "is",
    "mean",
    "of",
    "on",
    "or",
    "the",
    "to",
    "was",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
}


def tokenize(value: str) -> list[str]:
    return [token.casefold() for token in re.findall(r"[\w+#.-]{2,}", value)]


def meaningful_tokens(value: str) -> list[str]:
    return [_normalize_inflection(token) for token in tokenize(value) if token not in _STOP]


def _normalize_inflection(token: str) -> str:
    if len(token) > 5 and token.endswith("ies"):
        return f"{token[:-3]}y"
    if len(token) > 6 and token.endswith("ing"):
        base = token[:-3]
        return base[:-1] if len(base) > 3 and base[-1] == base[-2] else base
    if len(token) > 5 and token.endswith("ied"):
        return f"{token[:-3]}y"
    if len(token) > 5 and token.endswith("ed"):
        base = token[:-2]
        return base[:-1] if len(base) > 3 and base[-1] == base[-2] else base
    if len(token) > 5 and token.endswith(("sses", "shes", "ches", "xes", "zes")):
        return token[:-2]
    if len(token) > 4 and token.endswith("s") and not token.endswith(("ss", "us", "is")):
        return token[:-1]
    return token


def rank_passages(query: str, passages: list[Passage]) -> list[Passage]:
    if not passages:
        return []
    query_sequence = meaningful_tokens(query)
    query_terms = set(query_sequence)
    query_bigrams = set(pairwise(query_sequence))
    docs = [meaningful_tokens(f"{p.heading or ''} {p.text}") for p in passages]
    frequencies = Counter(term for doc in docs for term in set(doc))
    average_length = sum(map(len, docs)) / max(1, len(docs))
    for passage, terms in zip(passages, docs, strict=True):
        counts = Counter(terms)
        score = 0.0
        for term in query_terms:
            tf = counts[term]
            if not tf:
                continue
            idf = math.log(1 + (len(docs) - frequencies[term] + 0.5) / (frequencies[term] + 0.5))
            denominator = tf + 1.2 * (0.25 + 0.75 * len(terms) / max(1.0, average_length))
            score += idf * tf * 2.2 / denominator
        doc_bigrams = set(pairwise(terms))
        bigram_overlap = len(query_bigrams & doc_bigrams) / max(1, len(query_bigrams))
        term_coverage = len(query_terms & set(terms)) / max(1, len(query_terms))
        proximity_bonus = 0.0
        positions = {
            term: [index for index, candidate in enumerate(terms) if candidate == term]
            for term in query_terms & set(terms)
        }
        if len(positions) >= 2:
            minimum_distance = min(
                abs(left_position - right_position)
                for left_term, left_positions in positions.items()
                for right_term, right_positions in positions.items()
                if left_term < right_term
                for left_position in left_positions
                for right_position in right_positions
            )
            proximity_bonus = min(0.8, 1.6 / max(2, minimum_distance))
        phrase_bonus = 1.5 if query.casefold() in passage.text.casefold() else 0.0
        heading_bonus = 0.4 * len(query_terms & set(meaningful_tokens(passage.heading or "")))
        passage.relevance_score = (
            score
            + phrase_bonus
            + heading_bonus
            + 1.1 * bigram_overlap
            + 0.9 * term_coverage**2
            + proximity_bonus
        )
    maximum = max((passage.relevance_score for passage in passages), default=1.0) or 1.0
    for passage in passages:
        passage.relevance_score = round(min(1.0, passage.relevance_score / maximum), 4)
    return sorted(passages, key=lambda passage: passage.relevance_score, reverse=True)
