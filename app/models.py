from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class SearchMode(StrEnum):
    QUICK = "quick"
    STANDARD = "standard"
    DEEP = "deep"


class SearchResult(BaseModel):
    url: str
    title: str
    snippet: str = ""
    engine: str = "unknown"
    engines: list[str] = Field(default_factory=list)
    domain: str = ""
    canonical_url: str = ""
    published_at: datetime | None = None
    search_score: float = 0.0
    preliminary_score: float = 0.0


class FetchResult(BaseModel):
    requested_url: str
    final_url: str
    status_code: int
    content_type: str
    body: str
    headers: dict[str, str] = Field(default_factory=dict)
    method: Literal["http", "browser", "cache"] = "http"
    retrieved_at: datetime
    error: str | None = None


class ExtractedPage(BaseModel):
    url: str
    title: str
    text: str
    headings: list[str] = Field(default_factory=list)
    author: str | None = None
    site_name: str | None = None
    language: str | None = None
    canonical_url: str | None = None
    published_at: datetime | None = None
    updated_at: datetime | None = None
    content_hash: str
    extraction_method: str
    retrieved_at: datetime


class Passage(BaseModel):
    heading: str | None = None
    text: str
    start_offset: int
    end_offset: int
    relevance_score: float = 0.0
    injection_risk: Literal["low", "medium", "high"] = "low"
    injection_reasons: list[str] = Field(default_factory=list)


class SourceRecord(BaseModel):
    source_id: str
    url: str
    title: str
    domain: str
    published_at: datetime | None = None
    updated_at: datetime | None = None
    retrieved_at: datetime
    source_type: str
    quality_score: float
    quality_explanation: list[str] = Field(default_factory=list)
    relevance_score: float
    fetch_method: str
    content_hash: str


class EvidenceRecord(BaseModel):
    evidence_id: str
    source_id: str
    heading: str | None = None
    text: str
    start_offset: int
    end_offset: int
    relevance_score: float
    supports: list[str] = Field(default_factory=list)
    contradicts: list[str] = Field(default_factory=list)
    injection_risk: str = "low"
    content_boundary: str = "UNTRUSTED_WEB_EVIDENCE"
    citation: str


class Contradiction(BaseModel):
    topic: str
    evidence_ids: list[str]
    description: str
    severity: Literal["low", "medium", "high"] = "medium"


class CoverageReport(BaseModel):
    score: float
    status: Literal["insufficient", "weak", "moderate", "strong"]
    covered_topics: list[str] = Field(default_factory=list)
    missing_topics: list[str] = Field(default_factory=list)
    primary_source_present: bool = False
    independent_source_count: int = 0


class PrivacySummary(BaseModel):
    search_transport: str
    fetch_transport: str
    direct_egress_allowed: bool
    mode: str


class ResearchPackage(BaseModel):
    query: str
    mode: str
    request_id: str
    search_rounds: int
    coverage: CoverageReport
    sources: list[SourceRecord]
    evidence: list[EvidenceRecord]
    contradictions: list[Contradiction] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    failures: list[dict[str, str]] = Field(default_factory=list)
    privacy: PrivacySummary


class HealthReport(BaseModel):
    status: Literal["healthy", "degraded", "unhealthy"]
    components: dict[str, dict[str, Any]]
    privacy_mode: str
    unsafe_fallback_enabled: bool
