from __future__ import annotations

import math
import re
from collections import Counter

from app.models import Passage


def tokenize(value: str) -> list[str]:
    return [token.casefold() for token in re.findall(r"[\w+#.-]{2,}", value)]


def rank_passages(query: str, passages: list[Passage]) -> list[Passage]:
    if not passages:
        return []
    query_terms = set(tokenize(query))
    docs = [tokenize(f"{p.heading or ''} {p.text}") for p in passages]
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
        phrase_bonus = 1.5 if query.casefold() in passage.text.casefold() else 0.0
        heading_bonus = 0.4 * len(query_terms & set(tokenize(passage.heading or "")))
        passage.relevance_score = score + phrase_bonus + heading_bonus
    maximum = max((passage.relevance_score for passage in passages), default=1.0) or 1.0
    for passage in passages:
        passage.relevance_score = round(min(1.0, passage.relevance_score / maximum), 4)
    return sorted(passages, key=lambda passage: passage.relevance_score, reverse=True)
