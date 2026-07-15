from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path
from typing import Any

from app.models import SearchMode
from app.runtime import create_runtime
from benchmarks.baseline_searxng import run_baseline


async def evaluate(limit: int | None, run_timeout: float) -> None:
    questions = json.loads(Path("benchmarks/questions.json").read_text(encoding="utf-8"))
    if limit:
        questions = questions[:limit]
    runtime = create_runtime()
    raw_runs: list[dict[str, Any]] = []
    rows: list[str] = []
    for item in questions:
        question_id, question = item["id"], item["question"]
        for mode in ("raw_searxng", "quick", "standard", "deep"):
            print(f"START {question_id} {mode}", flush=True)
            started = time.monotonic()
            try:
                if mode == "raw_searxng":
                    result = await asyncio.wait_for(
                        run_baseline(runtime.pipeline.backend, question), timeout=run_timeout
                    )
                else:
                    package = await asyncio.wait_for(
                        runtime.pipeline.search_web(question, mode=SearchMode(mode), max_sources=8),
                        timeout=run_timeout,
                    )
                    result = package.model_dump(mode="json")
                error = ""
            except Exception as exc:
                result = {}
                error = type(exc).__name__
            elapsed = round(time.monotonic() - started, 3)
            run = {
                "question_id": question_id,
                "mode": mode,
                "elapsed": elapsed,
                "error": error,
                "result": result,
            }
            raw_runs.append(run)
            sources = result.get("sources", []) if result else []
            evidence = result.get("evidence", []) if result else []
            coverage = (result.get("coverage") or {}).get("score", "") if result else ""
            rows.append(
                f"| {question_id} | {mode} | {elapsed} | {len(sources)} | {len(evidence)} | {coverage} | {error or '—'} |"
            )
            print(f"DONE {question_id} {mode} {elapsed}s {error or 'ok'}", flush=True)
    output = Path("benchmarks/results")
    output.mkdir(parents=True, exist_ok=True)
    (output / "latest-raw.json").write_text(
        json.dumps(raw_runs, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    report = (
        """# Private Research benchmark\n\nNo answer-quality score is inferred automatically. Source relevance, citation support, freshness, and unsupported-claim risk require human review in `latest-human-review.json`.\n\n| Question | Mode | Latency s | Sources | Evidence | Coverage | Error |\n|---|---:|---:|---:|---:|---:|---|\n"""
        + "\n".join(rows)
        + "\n"
    )
    (output / "latest-report.md").write_text(report, encoding="utf-8")
    review = [
        {
            "question_id": item["id"],
            "source_precision": None,
            "passage_relevance": None,
            "citation_support": None,
            "freshness_appropriate": None,
            "unsupported_claim_risk": None,
            "notes": "",
        }
        for item in questions
    ]
    (output / "latest-human-review.json").write_text(json.dumps(review, indent=2), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int)
    parser.add_argument("--run-timeout", type=float, default=300.0)
    arguments = parser.parse_args()
    asyncio.run(evaluate(arguments.limit, arguments.run_timeout))
