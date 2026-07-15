from __future__ import annotations

import re

from selectolax.parser import HTMLParser

DROP_SELECTORS = (
    "script",
    "style",
    "noscript",
    "template",
    "form",
    "nav",
    "footer",
    "aside",
    "iframe",
    "[hidden]",
    "[aria-hidden='true']",
    ".cookie",
    ".advertisement",
    ".ads",
    ".sidebar",
)


def clean_html(html: str) -> str:
    tree = HTMLParser(re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL))
    for selector in DROP_SELECTORS:
        for node in tree.css(selector):
            node.decompose()
    for node in tree.css("*"):
        style = (node.attributes.get("style") or "").replace(" ", "").lower()
        if "display:none" in style or "visibility:hidden" in style:
            node.decompose()
    return tree.html or ""


def normalize_text(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
