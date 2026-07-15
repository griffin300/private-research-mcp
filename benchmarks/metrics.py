from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class RunMetrics:
    mode: str
    question_id: str
    latency_seconds: float
    source_count: int
    evidence_count: int
    duplicate_rate: float
    primary_source_rate: float
    coverage_score: float
    contradiction_count: int
    failure_count: int


def duplicate_rate(urls: list[str]) -> float:
    return 0.0 if not urls else 1.0 - len(set(urls)) / len(urls)
