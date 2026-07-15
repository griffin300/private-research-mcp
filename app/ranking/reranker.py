from __future__ import annotations

from app.models import Passage
from app.ranking.lexical import rank_passages


class HybridReranker:
    def rank(self, query: str, passages: list[Passage]) -> list[Passage]:
        # Lexical mode is always available. Local embeddings/cross-encoder are additive only.
        return rank_passages(query, passages)
