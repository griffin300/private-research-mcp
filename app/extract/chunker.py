from __future__ import annotations

import re

from app.models import Passage


def chunk_text(text: str, *, target_chars: int = 1200, max_chars: int = 1800) -> list[Passage]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    passages: list[Passage] = []
    buffer: list[str] = []
    buffer_length = 0
    cursor = 0
    heading: str | None = None
    for paragraph in paragraphs:
        if len(paragraph) <= 140 and not paragraph.endswith((".", "!", "?")):
            heading = paragraph
        if buffer and (
            buffer_length + len(paragraph) + 2 > max_chars or buffer_length >= target_chars
        ):
            joined = "\n\n".join(buffer)
            start = text.find(buffer[0], cursor)
            start = cursor if start < 0 else start
            end = start + len(joined)
            passages.append(
                Passage(heading=heading, text=joined, start_offset=start, end_offset=end)
            )
            cursor = end
            buffer = []
            buffer_length = 0
        if len(paragraph) > max_chars:
            sentences = re.split(r"(?<=[.!?])\s+", paragraph)
            for sentence in sentences:
                if buffer_length + len(sentence) + 1 > max_chars and buffer:
                    joined = " ".join(buffer)
                    start = text.find(buffer[0], cursor)
                    start = cursor if start < 0 else start
                    end = start + len(joined)
                    passages.append(
                        Passage(heading=heading, text=joined, start_offset=start, end_offset=end)
                    )
                    cursor, buffer, buffer_length = end, [], 0
                buffer.append(sentence)
                buffer_length += len(sentence) + 1
        else:
            buffer.append(paragraph)
            buffer_length += len(paragraph) + 2
    if buffer:
        joined = "\n\n".join(buffer)
        start = text.find(buffer[0], cursor)
        start = cursor if start < 0 else start
        passages.append(
            Passage(
                heading=heading, text=joined, start_offset=start, end_offset=start + len(joined)
            )
        )
    return passages
