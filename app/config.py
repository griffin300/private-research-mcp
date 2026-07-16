from __future__ import annotations

import ipaddress
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app import PROJECT_NAME


def _is_permitted_local_endpoint(value: str) -> bool:
    parsed = urlsplit(value)
    host = parsed.hostname
    if not host:
        return False
    if host in {"localhost", "host.docker.internal", "gateway.docker.internal"}:
        return True
    if "." not in host and host.replace("-", "").isalnum():
        return True  # Docker-internal service name.
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_loopback or address.is_private


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PRM_", env_file=".env", extra="ignore", case_sensitive=False
    )

    project_name: str = PROJECT_NAME
    privacy_mode: str = "strict"
    searxng_base_url: str = "http://searxng:8080"
    searxng_external_instance: bool = False
    search_proxy_url: str = "socks5://tor-search:9050"
    fetch_proxy_url: str = "socks5://tor-fetch:9050"
    direct_egress_allowed: bool = False
    admin_host: str = "127.0.0.1"
    admin_port: int = 8088
    mcp_host: str = "127.0.0.1"
    mcp_port: int = 8089
    containerized: bool = False
    database_path: Path = Path("/data/research.db")
    model_dir: Path = Path("/models")
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    reranker_model: str = "Xenova/ms-marco-MiniLM-L-6-v2"
    enable_embeddings: bool = False
    enable_reranker: bool = False
    enable_browser: bool = False
    browser_service_url: str = "http://browser-service:8090"
    store_search_history: bool = False
    cache_retention_days: int = Field(default=7, ge=0, le=365)
    log_raw_queries: bool = False
    log_level: str = "INFO"
    lm_studio_base_url: str = "http://host.docker.internal:1234/v1"
    lm_studio_model: str = ""
    lm_studio_planner_base_url: str = ""
    lm_studio_planner_model: str = ""
    allow_internal_llm_planner: bool = False
    allow_private_destinations: bool = False
    max_response_bytes: int = Field(default=5 * 1024 * 1024, ge=64 * 1024, le=50 * 1024 * 1024)
    request_timeout_seconds: float = Field(default=30.0, ge=1, le=120)
    robots_timeout_seconds: float = Field(default=15.0, ge=1, le=60)
    max_redirects: int = Field(default=4, ge=0, le=10)
    per_domain_concurrency: int = Field(default=2, ge=1, le=10)
    search_min_interval_seconds: float = Field(default=1.25, ge=0, le=10)
    searxng_recovery_delay_seconds: float = Field(default=10.5, ge=0, le=30)
    quick_queries: int = Field(default=3, ge=1, le=10)
    quick_raw_results: int = Field(default=15, ge=3, le=100)
    quick_pages: int = Field(default=5, ge=1, le=25)
    quick_passages: int = Field(default=10, ge=1, le=50)
    quick_rounds: int = Field(default=1, ge=1, le=4)
    quick_browser_pages: int = Field(default=0, ge=0, le=5)
    standard_queries: int = Field(default=6, ge=1, le=15)
    standard_raw_results: int = Field(default=40, ge=3, le=150)
    standard_pages: int = Field(default=10, ge=1, le=30)
    standard_passages: int = Field(default=20, ge=1, le=75)
    standard_rounds: int = Field(default=2, ge=1, le=4)
    standard_browser_pages: int = Field(default=1, ge=0, le=10)
    deep_queries: int = Field(default=15, ge=1, le=30)
    deep_raw_results: int = Field(default=100, ge=3, le=300)
    deep_pages: int = Field(default=25, ge=1, le=50)
    deep_passages: int = Field(default=40, ge=1, le=150)
    deep_rounds: int = Field(default=4, ge=1, le=6)
    deep_browser_pages: int = Field(default=3, ge=0, le=15)
    quick_deadline_seconds: float = Field(default=90.0, ge=30, le=1800)
    standard_deadline_seconds: float = Field(default=240.0, ge=30, le=1800)
    deep_deadline_seconds: float = Field(default=720.0, ge=30, le=1800)

    @model_validator(mode="after")
    def validate_security_boundaries(self) -> Settings:
        unsupported_ranking_features = [
            name
            for enabled, name in (
                (self.enable_embeddings, "enable_embeddings"),
                (self.enable_reranker, "enable_reranker"),
            )
            if enabled
        ]
        if unsupported_ranking_features:
            names = ", ".join(unsupported_ranking_features)
            raise ValueError(
                f"unsupported ranking capability flags ({names}); "
                "this build implements lexical ranking only"
            )
        if self.privacy_mode not in {"strict", "development"}:
            raise ValueError("privacy_mode must be 'strict' or 'development'")
        if self.privacy_mode == "strict":
            if self.direct_egress_allowed:
                raise ValueError("strict privacy mode forbids direct egress")
            if not self.fetch_proxy_url or not self.search_proxy_url:
                raise ValueError("strict privacy mode requires separate search and fetch proxies")
            if self.fetch_proxy_url == self.search_proxy_url:
                raise ValueError("search and fetch proxies must be distinct")
        for host in (self.admin_host, self.mcp_host):
            allowed = {"127.0.0.1", "localhost"}
            if self.containerized:
                allowed.add("0.0.0.0")  # noqa: S104 - host publication remains loopback-only.
            if host not in allowed:
                raise ValueError("host interfaces must be loopback unless explicitly containerized")
        if self.allow_internal_llm_planner:
            if not self.lm_studio_planner_base_url or not self.lm_studio_planner_model:
                raise ValueError("enhanced planner needs a URL and model")
            if not _is_permitted_local_endpoint(self.lm_studio_planner_base_url):
                raise ValueError("planner endpoint must be local or private")
            if self.lm_studio_planner_base_url.rstrip("/") == self.lm_studio_base_url.rstrip("/"):
                raise ValueError(
                    "planner endpoint must be separate from the primary LM Studio endpoint"
                )
        return self
