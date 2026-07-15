from __future__ import annotations

import hashlib
from datetime import datetime

import trafilatura
from dateutil import parser as date_parser
from readability import Document  # type: ignore[import-untyped]
from selectolax.parser import HTMLParser

from app.extract.cleaner import clean_html, normalize_text
from app.extract.metadata import extract_metadata
from app.models import ExtractedPage, FetchResult


class ExtractionError(RuntimeError):
    pass


class PageExtractor:
    def extract(self, fetched: FetchResult) -> ExtractedPage:
        if fetched.content_type == "text/plain":
            text, method = normalize_text(fetched.body), "plain"
            metadata: dict[str, object] = {"title": fetched.final_url}
        else:
            metadata = extract_metadata(fetched.body)
            sanitized = clean_html(fetched.body)
            text = (
                trafilatura.extract(
                    sanitized,
                    output_format="txt",
                    include_comments=False,
                    include_tables=True,
                    favor_precision=True,
                )
                or ""
            )
            method = "trafilatura"
            if len(text) < 200:
                tree = HTMLParser(sanitized)
                main = tree.css_first("main") or tree.css_first("article") or tree.body
                text = main.text(separator="\n", strip=True) if main else ""
                method = "selectolax"
            if len(text) < 200:
                summary = Document(sanitized).summary(html_partial=True)
                tree = HTMLParser(summary)
                text = tree.text(separator="\n", strip=True)
                method = "readability"
            text = normalize_text(text)
        if metadata.get("updated_at") is None and fetched.headers.get("last-modified"):
            try:
                metadata["updated_at"] = date_parser.parse(fetched.headers["last-modified"])
            except (ValueError, OverflowError):
                pass
        if len(text) < 80:
            raise ExtractionError("page did not contain enough extractable text")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return ExtractedPage(
            url=fetched.final_url,
            title=str(metadata.get("title") or fetched.final_url),
            text=text,
            author=_optional_str(metadata.get("author")),
            site_name=_optional_str(metadata.get("site_name")),
            language=_optional_str(metadata.get("language")),
            canonical_url=_optional_str(metadata.get("canonical_url")),
            published_at=_optional_datetime(metadata.get("published_at")),
            updated_at=_optional_datetime(metadata.get("updated_at")),
            content_hash=digest,
            extraction_method=method,
            retrieved_at=fetched.retrieved_at,
        )


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _optional_datetime(value: object) -> datetime | None:
    return value if isinstance(value, datetime) else None
