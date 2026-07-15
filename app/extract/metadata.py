from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from dateutil import parser as date_parser
from selectolax.parser import HTMLParser


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return date_parser.parse(value)
    except (ValueError, OverflowError):
        return None


def extract_metadata(html: str) -> dict[str, Any]:
    tree = HTMLParser(html)
    title_node = tree.css_first("title")
    data: dict[str, Any] = {"title": title_node.text(strip=True) if title_node else "Untitled"}
    mapping = {
        "og:title": "title",
        "og:site_name": "site_name",
        "article:published_time": "published_at",
        "article:modified_time": "updated_at",
    }
    for node in tree.css("meta"):
        key = node.attributes.get("property") or node.attributes.get("name") or ""
        content = node.attributes.get("content")
        if key in mapping and content:
            data[mapping[key]] = content
        if key.lower() == "author" and content:
            data["author"] = content
    canonical = tree.css_first("link[rel='canonical']")
    if canonical and canonical.attributes.get("href"):
        data["canonical_url"] = canonical.attributes["href"]
    html_node = tree.css_first("html")
    if html_node and html_node.attributes.get("lang"):
        data["language"] = html_node.attributes["lang"]
    for script in tree.css("script[type='application/ld+json']"):
        try:
            value = json.loads(script.text())
        except (json.JSONDecodeError, ValueError):
            continue
        items = value if isinstance(value, list) else [value]
        for item in items:
            if not isinstance(item, dict):
                continue
            data.setdefault("author", _author_name(item.get("author")))
            data.setdefault("published_at", item.get("datePublished"))
            data.setdefault("updated_at", item.get("dateModified"))
    data["published_at"] = _parse_date(data.get("published_at"))
    data["updated_at"] = _parse_date(data.get("updated_at"))
    return data


def _author_name(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and isinstance(value.get("name"), str):
        return str(value["name"])
    if isinstance(value, list):
        names = [name for item in value if (name := _author_name(item))]
        return ", ".join(names) or None
    return None
