from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.models import ResearchPackage  # noqa: E402
from app.orchestration.response import research_response  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Measure full versus compact MCP research response size."
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("--budget", type=int, default=14_000)
    parser.add_argument(
        "--questions",
        type=Path,
        default=Path("benchmarks/answer_quality_questions.json"),
    )
    args = parser.parse_args()

    rows = json.loads(args.input.read_text(encoding="utf-8"))
    question_items = json.loads(args.questions.read_text(encoding="utf-8"))
    questions = {str(item["id"]): item for item in question_items}
    measurements: list[dict[str, float | int]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        result = row.get("result")
        if not isinstance(result, dict) or not {
            "coverage",
            "sources",
            "evidence",
            "privacy",
        }.issubset(result):
            continue
        package = ResearchPackage.model_validate(result)
        full = package.model_dump(mode="json")
        compact = research_response(package, max_chars=args.budget)
        full_chars = _chars(full)
        compact_chars = _chars(compact)
        assertions = questions.get(str(row.get("question_id")), {}).get("assertions", [])
        full_context = _visible_context(full)
        compact_context = _visible_context(compact)
        facts_before = sum(_assertion_visible(full_context, item) for item in assertions)
        facts_after = sum(_assertion_visible(compact_context, item) for item in assertions)
        full_citations = {
            str(item.get("citation"))
            for key in ("evidence", "search_snippets")
            for item in full.get(key, [])
            if isinstance(item, dict) and item.get("citation")
        }
        compact_citations = {
            str(item.get("citation"))
            for key in ("evidence", "search_snippets")
            for item in compact.get(key, [])
            if isinstance(item, dict) and item.get("citation")
        }
        measurements.append(
            {
                "full": full_chars,
                "compact": compact_chars,
                "reduction": 1 - compact_chars / max(1, full_chars),
                "evidence_before": len(package.evidence),
                "evidence_after": len(compact["evidence"]),
                "snippets_before": len(package.search_snippets),
                "snippets_after": len(compact["search_snippets"]),
                "facts_before": facts_before,
                "facts_after": facts_after,
                "invalid_citations": len(compact_citations - full_citations),
            }
        )
    if not measurements:
        raise SystemExit("No ResearchPackage results found in input")

    print(f"packages={len(measurements)} budget={args.budget}")
    print(
        "full_chars "
        f"median={_median(measurements, 'full'):.0f} "
        f"max={max(item['full'] for item in measurements):.0f}"
    )
    print(
        "compact_chars "
        f"median={_median(measurements, 'compact'):.0f} "
        f"max={max(item['compact'] for item in measurements):.0f}"
    )
    print(
        "reduction "
        f"median={_median(measurements, 'reduction'):.1%} "
        f"min={min(item['reduction'] for item in measurements):.1%}"
    )
    print(f"budget_overruns={sum(item['compact'] > args.budget for item in measurements)}")
    print(
        "evidence_omitted="
        f"{sum(item['evidence_before'] - item['evidence_after'] for item in measurements):.0f}"
    )
    print(
        "snippets_omitted="
        f"{sum(item['snippets_before'] - item['snippets_after'] for item in measurements):.0f}"
    )
    print(
        "visible_fact_hits="
        f"{sum(item['facts_after'] for item in measurements):.0f}/"
        f"{sum(item['facts_before'] for item in measurements):.0f} "
        f"lost={sum(item['facts_before'] - item['facts_after'] for item in measurements):.0f}"
    )
    print(
        f"invalid_compact_citations={sum(item['invalid_citations'] for item in measurements):.0f}"
    )


def _chars(value: dict[str, Any]) -> int:
    return len(json.dumps(value, ensure_ascii=False))


def _median(values: list[dict[str, float | int]], key: str) -> float:
    return statistics.median(float(item[key]) for item in values)


def _visible_context(result: dict[str, Any]) -> str:
    values: list[str] = []
    for key in ("evidence", "search_snippets"):
        for item in result.get(key, []):
            if isinstance(item, dict):
                values.append(f"{item.get('title', '')} {item.get('text', '')}")
    return "\n".join(values)


def _assertion_visible(context: str, assertion: dict[str, Any]) -> bool:
    return any(
        re.search(pattern, context, re.IGNORECASE) is not None
        for pattern in assertion.get("patterns", [])
    )


if __name__ == "__main__":
    main()
