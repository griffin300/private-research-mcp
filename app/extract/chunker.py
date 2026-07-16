from __future__ import annotations

import re
from collections.abc import Iterator

from app.models import Passage

_PARAGRAPH_SEPARATOR = re.compile(r"\r?\n(?:[ \t]*\r?\n)+")
_SENTENCE_SEPARATOR = re.compile(r"(?<=[.!?])\s+")


def _trimmed_span(text: str, start: int, end: int) -> tuple[int, int] | None:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return (start, end) if start < end else None


def _paragraph_spans(text: str) -> Iterator[tuple[int, int]]:
    start = 0
    for separator in _PARAGRAPH_SEPARATOR.finditer(text):
        span = _trimmed_span(text, start, separator.start())
        if span is not None:
            yield span
        start = separator.end()
    span = _trimmed_span(text, start, len(text))
    if span is not None:
        yield span


def _sentence_spans(text: str, start: int, end: int) -> Iterator[tuple[int, int]]:
    sentence_start = start
    for separator in _SENTENCE_SEPARATOR.finditer(text, start, end):
        span = _trimmed_span(text, sentence_start, separator.start())
        if span is not None:
            yield span
        sentence_start = separator.end()
    span = _trimmed_span(text, sentence_start, end)
    if span is not None:
        yield span


def chunk_text(text: str, *, target_chars: int = 1200, max_chars: int = 1800) -> list[Passage]:
    passages: list[Passage] = []
    current_heading: str | None = None
    buffer_heading: str | None = None
    buffer_start: int | None = None
    buffer_end: int | None = None

    def flush() -> None:
        nonlocal buffer_heading, buffer_start, buffer_end
        if buffer_start is None or buffer_end is None:
            return
        passages.append(
            Passage(
                heading=buffer_heading,
                text=text[buffer_start:buffer_end],
                start_offset=buffer_start,
                end_offset=buffer_end,
            )
        )
        buffer_heading = None
        buffer_start = None
        buffer_end = None

    def append_span(start: int, end: int) -> None:
        nonlocal buffer_heading, buffer_start, buffer_end
        if buffer_start is not None and buffer_end is not None:
            if end - buffer_start > max_chars or buffer_end - buffer_start >= target_chars:
                flush()
        if buffer_start is None:
            buffer_heading = current_heading
            buffer_start = start
        buffer_end = end

    for paragraph_start, paragraph_end in _paragraph_spans(text):
        paragraph = text[paragraph_start:paragraph_end]
        is_heading = len(paragraph) <= 140 and not paragraph.endswith((".", "!", "?"))
        if is_heading:
            flush()
            current_heading = paragraph

        spans: Iterator[tuple[int, int]]
        if paragraph_end - paragraph_start > max_chars:
            spans = _sentence_spans(text, paragraph_start, paragraph_end)
        else:
            spans = iter(((paragraph_start, paragraph_end),))
        for start, end in spans:
            append_span(start, end)

    flush()
    return passages
