from __future__ import annotations

import re
from dataclasses import dataclass

PATTERNS: dict[str, re.Pattern[str]] = {
    "instruction_override": re.compile(
        r"ignore\s+(?:all\s+)?(?:previous|prior|system)(?:\s+system)?\s+instructions", re.I
    ),
    "secret_exfiltration": re.compile(
        r"(reveal|print|send|exfiltrate).{0,40}(secret|token|password|environment variable)", re.I
    ),
    "tool_invocation": re.compile(
        r"(call|invoke|execute|run).{0,30}(tool|command|shell|terminal)", re.I
    ),
    "role_override": re.compile(r"(system|assistant)\s*(message|prompt|instruction)\s*:", re.I),
    "local_file": re.compile(r"(read|open|upload).{0,30}(local file|/etc/|\.env|C:\\\\)", re.I),
}


@dataclass(frozen=True, slots=True)
class InjectionAssessment:
    risk: str
    reasons: list[str]


def assess_injection(text: str) -> InjectionAssessment:
    reasons = [name for name, pattern in PATTERNS.items() if pattern.search(text)]
    risk = (
        "high"
        if len(reasons) >= 2 or "instruction_override" in reasons
        else "medium"
        if reasons
        else "low"
    )
    return InjectionAssessment(risk, reasons)


def wrap_untrusted(text: str) -> str:
    return f"<UNTRUSTED_WEB_EVIDENCE>\n{text}\n</UNTRUSTED_WEB_EVIDENCE>"
