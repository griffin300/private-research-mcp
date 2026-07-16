from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import statistics
import time
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from app.orchestration.routing import select_search_mode
from app.runtime import create_runtime
from benchmarks.baseline_searxng import run_baseline

MODES = ("raw_searxng", "adaptive_hybrid")
DEFAULT_SEED = 20260714


def score_result(item: dict[str, Any], mode: str, result: dict[str, Any]) -> dict[str, Any]:
    sources = result.get("sources") if isinstance(result.get("sources"), list) else []
    evidence = result.get("evidence") if isinstance(result.get("evidence"), list) else []
    snippets = (
        result.get("search_snippets") if isinstance(result.get("search_snippets"), list) else []
    )
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
                contexts.append(
                    {
                        "text": text,
                        "citation": "",
                        "traceable": bool(source.get("url")),
                        "kind": "snippet",
                    }
                )
    else:
        for snippet in snippets:
            if not isinstance(snippet, dict) or snippet.get("injection_risk") == "high":
                continue
            text = f"{snippet.get('title', '')} {snippet.get('text', '')}".strip()
            snippet_id = str(snippet.get("snippet_id", ""))
            expected = f"[{snippet_id}]"
            if text:
                contexts.append(
                    {
                        "text": text,
                        "citation": str(snippet.get("citation", "")),
                        "citation_valid": (
                            bool(snippet.get("url"))
                            and snippet.get("verification") == "snippet_only"
                            and str(snippet.get("citation", "")) == expected
                        ),
                        "traceable": bool(snippet.get("url")),
                        "kind": "snippet",
                    }
                )
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
                        "traceable": (
                            source_id in source_ids
                            and str(record.get("citation", "")) == expected
                            and offsets_valid
                        ),
                        "kind": "evidence",
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
            for source in sources + snippets
            if isinstance(source, dict)
        )
    )

    evidence_contexts = [context for context in contexts if context.get("kind") == "evidence"]
    snippet_contexts = [context for context in contexts if context.get("kind") == "snippet"]
    valid_citations = sum(bool(context.get("citation_valid")) for context in evidence_contexts)
    citation_integrity = valid_citations / max(1, len(evidence_contexts))
    snippet_traceability = sum(
        bool(context.get("traceable")) for context in snippet_contexts
    ) / max(1, len(snippet_contexts))
    context_traceability = sum(bool(context.get("traceable")) for context in contexts) / max(
        1, len(contexts)
    )
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
        + 0.15 * context_traceability
    )
    return {
        "fact_recall": round(fact_recall, 4),
        "fact_bearing_context_precision": round(fact_precision, 4),
        "preferred_source_hit": preferred_source_hit,
        "citation_integrity": round(citation_integrity, 4),
        "snippet_traceability": round(snippet_traceability, 4),
        "context_traceability": round(context_traceability, 4),
        "cited_fact_recall": round(cited_fact_recall, 4),
        "answer_readiness_score": round(readiness, 2),
        "assertions": assertion_rows,
        "answer_excerpt": contexts[:3],
    }


async def evaluate(
    limit: int | None, run_timeout: float, max_sources: int, repeats: int, seed: int
) -> None:
    questions: list[dict[str, Any]] = json.loads(
        Path("benchmarks/answer_quality_questions.json").read_text(encoding="utf-8")
    )
    if limit:
        questions = questions[:limit]
    random.Random(seed).shuffle(questions)  # noqa: S311 - deterministic benchmark ordering.
    runtime = create_runtime()
    runs: list[dict[str, Any]] = []
    for question_index, item in enumerate(questions):
        # A missing shared snapshot invalidates the pair, so fail loudly instead of
        # letting expansion make the hybrid appear to win against an empty baseline.
        snapshot_started = time.monotonic()
        exact_snapshot = await asyncio.wait_for(
            runtime.pipeline.search_exact(str(item["question"]), limit=10),
            timeout=run_timeout,
        )
        snapshot_elapsed = round(time.monotonic() - snapshot_started, 3)
        if not exact_snapshot:
            raise RuntimeError(f"shared exact-query snapshot is empty for {item['id']}")
        for repetition in range(1, repeats + 1):
            modes = list(MODES)
            if (question_index + repetition + seed) % 2:
                modes.reverse()
            for mode in modes:
                print(f"START {item['id']} r{repetition} {mode}", flush=True)
                started = time.monotonic()
                error = ""
                result: dict[str, Any] = {}
                try:
                    if mode == "raw_searxng":
                        result = await asyncio.wait_for(
                            run_baseline(
                                runtime.pipeline,
                                item["question"],
                                exact_results=exact_snapshot,
                            ),
                            timeout=run_timeout,
                        )
                    else:
                        selected_mode = select_search_mode(str(item["question"]))
                        package = await asyncio.wait_for(
                            runtime.pipeline.search_web(
                                item["question"],
                                mode=selected_mode,
                                max_sources=max_sources,
                                exact_results_override=exact_snapshot,
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
                        "repeat": repetition,
                        "snapshot_elapsed": snapshot_elapsed,
                        "elapsed": elapsed,
                        "end_to_end_elapsed": round(snapshot_elapsed + elapsed, 3),
                        "error": error,
                        "metrics": metrics,
                        "result": result,
                    }
                )
                print(
                    f"DONE {item['id']} r{repetition} {mode} {elapsed}s "
                    f"score={metrics['answer_readiness_score']} {error or 'ok'}",
                    flush=True,
                )
    _write_outputs(runs, len(questions), seed=seed, repeats=repeats)


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
    _write_outputs(
        runs,
        len({str(run["question_id"]) for run in runs}),
        seed=DEFAULT_SEED,
        repeats=max(int(run.get("repeat", 1)) for run in runs),
    )


def _write_outputs(
    runs: list[dict[str, Any]], question_count: int, *, seed: int, repeats: int
) -> None:
    output = Path("benchmarks/results")
    output.mkdir(parents=True, exist_ok=True)
    (output / "latest-answer-quality-raw.json").write_text(
        json.dumps(runs, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for run in runs:
        grouped[str(run["mode"])].append(run)
    aggregate_rows: list[str] = []
    report_modes = [mode for mode in MODES if grouped.get(mode)] + sorted(
        mode for mode in grouped if mode not in MODES
    )
    for mode in report_modes:
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
                    _mean(mode_runs, "context_traceability"),
                    _mean(mode_runs, "cited_fact_recall"),
                    _mean(mode_runs, "answer_readiness_score", digits=2),
                    f"{statistics.mean(float(run['elapsed']) for run in mode_runs):.2f}",
                    f"{statistics.mean(float(run.get('end_to_end_elapsed', run['elapsed'])) for run in mode_runs):.2f}",
                    str(sum(bool(run["error"]) for run in mode_runs)),
                )
            )
            + " |"
        )
    detail_rows = [
        f"| {run['question_id']} | {run['mode']} | {run['metrics']['fact_recall']:.2f} | "
        f"{run['metrics']['fact_bearing_context_precision']:.2f} | "
        f"{run['metrics']['preferred_source_hit']:.0f} | "
        f"{run['metrics']['citation_integrity']:.2f} | "
        f"{run['metrics']['context_traceability']:.2f} | "
        f"{run['metrics']['answer_readiness_score']:.2f} | {run['elapsed']:.2f} | "
        f"{float(run.get('end_to_end_elapsed', run['elapsed'])):.2f} | "
        f"{run['error'] or '—'} |"
        for run in runs
    ]
    report = f"""# Paired gold-fact answer-quality benchmark

Questions: {question_count}. Repetitions: {repeats}. Seed: {seed}. Headline systems: raw SearXNG and quality-first adaptive hybrid.

This is a deterministic **answer-readiness** benchmark, not an LLM-as-judge score. The harness freezes one exact-query top-10 snapshot per question and supplies it to both systems; the hybrid adds query expansion, safe page extraction, source selection, and evidence ranking. Run order alternates to reduce order bias. Each question has hand-authored expected facts expressed as transparent regex alternatives plus preferred primary-source domains. Post-snapshot latency isolates each system's added work; end-to-end retrieval latency adds the measured shared SearXNG snapshot time back to both systems.

The composite is: 55% gold-fact recall, 15% fact-bearing-context precision, 15% preferred-source hit, and 15% context traceability. Extracted-evidence citation integrity remains a separate diagnostic and validates source IDs, exact citation rendering, nonempty passage text, and offsets; it does not claim semantic entailment. When the local API is available, final answer synthesis is scored separately by `benchmarks.synthesize_answers`.

## Aggregate

| Mode | Fact recall | Fact-context precision | Preferred source | Evidence citation integrity | Context traceability | Cited fact recall | Readiness /100 | Post-snapshot s | End-to-end retrieval s | Errors |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(aggregate_rows)}

## Per question

| Question | Mode | Fact recall | Fact-context precision | Preferred source | Evidence citation integrity | Context traceability | Readiness /100 | Post-snapshot s | End-to-end retrieval s | Error |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
{chr(10).join(detail_rows)}

Full assertion hits, excerpts, source metadata, and failures are written to the local generated artifact `latest-answer-quality-raw.json`, which is intentionally ignored by Git.
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
    parser.add_argument("--run-timeout", type=float, default=840.0)
    parser.add_argument("--max-sources", type=int, default=8)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--rescore-only", action="store_true")
    arguments = parser.parse_args()
    if arguments.rescore_only:
        rescore_existing()
    else:
        asyncio.run(
            evaluate(
                arguments.limit,
                arguments.run_timeout,
                arguments.max_sources,
                max(1, arguments.repeats),
                arguments.seed,
            )
        )
