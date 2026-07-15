from __future__ import annotations

import re
from collections import defaultdict

from app.models import Contradiction, EvidenceRecord

_VALUE = re.compile(r"\b(?:v(?:ersion)?\s*)?(\d+(?:\.\d+){0,3})(?:\s*(%|ms|gb|mb|usd|\$))?\b", re.I)


def detect_contradictions(evidence: list[EvidenceRecord]) -> list[Contradiction]:
    values: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for record in evidence:
        words = re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", record.text.lower())
        topic = " ".join(words[:4])
        for number, unit in _VALUE.findall(record.text):
            values[f"{topic}|{unit.lower()}"].append((number, record.evidence_id))
    contradictions: list[Contradiction] = []
    for key, claims in values.items():
        distinct = {value for value, _ in claims}
        source_ids = list(dict.fromkeys(record for _, record in claims))
        if len(distinct) > 1 and len(source_ids) > 1:
            contradictions.append(
                Contradiction(
                    topic=key.split("|", 1)[0],
                    evidence_ids=source_ids,
                    description=f"Conflicting numeric or version values found: {', '.join(sorted(distinct))}",
                )
            )
    return contradictions[:10]
