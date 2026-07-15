from __future__ import annotations

import argparse
import asyncio
import json
import re
import statistics
import time
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from app.models import SearchMode
from app.runtime import create_runtime
from benchmarks.baseline_searxng import run_baseline

MODES = ("raw_searxng", "quick", "standard", "deep")


def score_result(item: dict[str, Any], mode: str, result: dict[str, Any]) -> dict[str, Any]:
    sources = result.get("sources") if isinstance(result.get("sources"), list) else []
    evidence = result.get("evidence") if isinstance(result.get("evidence"), list) else []
    source_ids = {
        str(source.get("source_id"))
        for source in sources
        if isinstance(source, dict) and source.get("source_id")
    }

    contexts: list[dict[str, Any]] = []
    if mode == "raw_searxng":
        for source in sources:
            if not isinstance(source, dict):
                continue
            text = f"{source.get('title', '')} {source.get('snippet', '')}".strip()
            if text:
                contexts.append({"text": text, "citation": ""})
    else:
        for record in evidence:
            if not isinstance(record, dict):
                continue
            text = str(record.get("text", "")).strip()
            if text:
                evidence_id = str(record.get("evidence_id", ""))
                source_id = str(record.get("source_id", ""))
                expected = f"[{source_id}, {evidence_id}]"
                offsets_valid = (
                    isinstance(record.get("start_offset"), int)
                    and isinstance(record.get("end_offset"), int)
                    and int(record["start_offset"]) >= 0
                    and int(record["end_offset"]) > int(record["start_offset"])
                )
                contexts.append(
                    {
                        "text": text,
                        "citation": str(record.get("citation", "")),
                        "citation_valid": (
                            source_id in source_ids
                            and str(record.get("citation", "")) == expected
                            and offsets_valid
                        ),
                    }
                )

    assertion_rows: list[dict[str, object]] = []
    for assertion in item["assertions"]:
        matching_contexts = [
            index
            for index, context in enumerate(contexts)
            if _matches_any(context["text"], assertion["patterns"])
        ]
        assertion_rows.append(
            {
                "label": assertion["label"],
                "hit": bool(matching_contexts),
                "context_indexes": matching_contexts,
            }
        )

    assertion_count = len(assertion_rows)
    fact_recall = sum(bool(row["hit"]) for row in assertion_rows) / max(1, assertion_count)
    fact_contexts = sum(
        any(
            _matches_any(context["text"], assertion["patterns"]) for assertion in item["assertions"]
        )
        for context in contexts
    )
    fact_precision = fact_contexts / max(1, len(contexts))
    preferred_source_hit = float(
        any(
            _preferred_domain(_source_domain(source), item["preferred_domains"])
            for source in sources
            if isinstance(source, dict)
        )
    )

    valid_citations = sum(bool(context.get("citation_valid")) for context in contexts)
    citation_integrity = valid_citations / max(1, len(evidence))
    cited_fact_recall = (
        sum(
            any(
                index < len(contexts)
                and bool(contexts[index].get("citation_valid"))
                and _matches_any(contexts[index]["text"], assertion["patterns"])
                for index in range(len(contexts))
            )
            for assertion in item["assertions"]
        )
        / max(1, assertion_count)
        if mode != "raw_searxng"
        else 0.0
    )
    readiness = 100 * (
        0.55 * fact_recall
        + 0.15 * fact_precision
        + 0.15 * preferred_source_hit
        + 0.15 * citation_integrity
    )
    return {
        "fact_recall": round(fact_recall, 4),
        "fact_bearing_context_precision": round(fact_precision, 4),
        "preferred_source_hit": preferred_source_hit,
        "citation_integrity": round(citation_integrity, 4),
        "cited_fact_recall": round(cited_fact_recall, 4),
        "answer_readiness_score": round(readiness, 2),
        "assertions": assertion_rows,
        "answer_excerpt": contexts[:3],
    }


async def evaluate(limit: int | None, run_timeout: float, max_sources: int) -> None:
    questions: list[dict[str, Any]] = json.loads(
        Path("benchmarks/answer_quality_questions.json").read_text(encoding="utf-8")
    )
    if limit:
        questions = questions[:limit]
    runtime = create_runtime()
    runs: list[dict[str, Any]] = []
    for item in questions:
        for mode in MODES:
            print(f"START {item['id']} {mode}", flush=True)
            started = time.monotonic()
            error = ""
            result: dict[str, Any] = {}
            try:
                if mode == "raw_searxng":
                    result = await asyncio.wait_for(
                        run_baseline(runtime.pipeline.backend, item["question"]),
                        timeout=run_timeout,
                    )
                else:
                    package = await asyncio.wait_for(
                        runtime.pipeline.search_web(
                            item["question"],
                            mode=SearchMode(mode),
                            max_sources=max_sources,
                        ),
                        timeout=run_timeout,
                    )
                    result = package.model_dump(mode="json")
                metrics = score_result(item, mode, result)
            except Exception as exc:
                error = type(exc).__name__
                metrics = score_result(item, mode, {})
            elapsed = round(time.monotonic() - started, 3)
            runs.append(
                {
                    "question_id": item["id"],
                    "category": item["category"],
                    "question": item["question"],
                    "mode": mode,
                    "elapsed": elapsed,
                    "error": error,
                    "metrics": metrics,
                    "result": result,
                }
            )
            print(
                f"DONE {item['id']} {mode} {elapsed}s score={metrics['answer_readiness_score']} {error or 'ok'}",
                flush=True,
            )
    _write_outputs(runs, len(questions))


def rescore_existing() -> None:
    path = Path("benchmarks/results/latest-answer-quality-raw.json")
    runs: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    questions: list[dict[str, Any]] = json.loads(
        Path("benchmarks/answer_quality_questions.json").read_text(encoding="utf-8")
    )
    items = {item["id"]: item for item in questions}
    for run in runs:
        run["metrics"] = score_result(
            items[str(run["question_id"])], str(run["mode"]), run["result"]
        )
    _write_outputs(runs, len({str(run["question_id"]) for run in runs}))


def _write_outputs(runs: list[dict[str, Any]], question_count: int) -> None:
    output = Path("benchmarks/results")
    output.mkdir(parents=True, exist_ok=True)
    (output / "latest-answer-quality-raw.json").write_text(
        json.dumps(runs, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for run in runs:
        grouped[str(run["mode"])].append(run)
    aggregate_rows: list[str] = []
    for mode in MODES:
        mode_runs = grouped[mode]
        aggregate_rows.append(
            "| "
            + " | ".join(
                (
                    mode,
                    _mean(mode_runs, "fact_recall"),
                    _mean(mode_runs, "fact_bearing_context_precision"),
                    _mean(mode_runs, "preferred_source_hit"),
                    _mean(mode_runs, "citation_integrity"),
                    _mean(mode_runs, "cited_fact_recall"),
                    _mean(mode_runs, "answer_readiness_score", digits=2),
                    f"{statistics.mean(float(run['elapsed']) for run in mode_runs):.2f}",
                    str(sum(bool(run["error"]) for run in mode_runs)),
                )
            )
            + " |"
        )
    detail_rows = [
        f"| {run['question_id']} | {run['mode']} | {run['metrics']['fact_recall']:.2f} | "
        f"{run['metrics']['fact_bearing_context_precision']:.2f} | "
        f"{run['metrics']['preferred_source_hit']:.0f} | {run['metrics']['citation_integrity']:.2f} | "
        f"{run['metrics']['answer_readiness_score']:.2f} | {run['elapsed']:.2f} | {run['error'] or '—'} |"
        for run in runs
    ]
    report = f"""# Gold-fact answer-quality benchmark

Questions: {question_count}. Modes: raw SearXNG, quick, standard, deep.

This is a deterministic **answer-readiness** benchmark, not an LLM-as-judge score. Each question has hand-authored expected facts expressed as transparent regex alternatives plus preferred primary-source domains. The candidate answer context is SearXNG title/snippet text for the raw baseline and extracted evidence passages for research modes.

The composite is: 55% gold-fact recall, 15% fact-bearing-context precision, 15% preferred-source hit, and 15% citation integrity. Citation integrity validates evidence/source IDs, exact citation rendering, nonempty passage text, and offsets; it does not claim semantic entailment. When the local API is available, final answer synthesis is scored separately by `benchmarks.synthesize_answers`.

## Aggregate

| Mode | Fact recall | Fact-context precision | Preferred source | Citation integrity | Cited fact recall | Readiness /100 | Mean latency s | Errors |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(aggregate_rows)}

## Per question

| Question | Mode | Fact recall | Fact-context precision | Preferred source | Citation integrity | Readiness /100 | Latency s | Error |
|---|---|---:|---:|---:|---:|---:|---:|---|
{chr(10).join(detail_rows)}

Full assertion hits, excerpts, source metadata, and failures are in `latest-answer-quality-raw.json`.
"""
    (output / "latest-answer-quality-report.md").write_text(report, encoding="utf-8")


def _mean(runs: list[dict[str, Any]], key: str, *, digits: int = 4) -> str:
    return f"{statistics.mean(float(run['metrics'][key]) for run in runs):.{digits}f}"


def _matches_any(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL) for pattern in patterns)


def _source_domain(source: dict[str, Any]) -> str:
    domain = str(source.get("domain", "")).lower().rstrip(".")
    return domain or (urlsplit(str(source.get("url", ""))).hostname or "").lower().rstrip(".")


def _preferred_domain(domain: str, preferred: list[str]) -> bool:
    return any(domain == item or domain.endswith(f".{item}") for item in preferred)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run deterministic gold-fact answer scoring")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--run-timeout", type=float, default=60.0)
    parser.add_argument("--max-sources", type=int, default=6)
    parser.add_argument("--rescore-only", action="store_true")
    arguments = parser.parse_args()
    if arguments.rescore_only:
        rescore_existing()
    else:
        asyncio.run(evaluate(arguments.limit, arguments.run_timeout, arguments.max_sources))
