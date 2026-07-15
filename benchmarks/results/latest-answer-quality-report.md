# Paired gold-fact answer-quality benchmark

Questions: 6. Repetitions: 3. Seed: 20260714. Headline systems: raw SearXNG and quality-first adaptive hybrid.

This is a deterministic **answer-readiness** benchmark, not an LLM-as-judge score. The harness freezes one exact-query top-10 snapshot per question and supplies it to both systems; the hybrid adds query expansion, safe page extraction, source selection, and evidence ranking. Run order alternates to reduce order bias. Each question has hand-authored expected facts expressed as transparent regex alternatives plus preferred primary-source domains. Latency starts after the shared snapshot and is diagnostic only.

The composite is: 55% gold-fact recall, 15% fact-bearing-context precision, 15% preferred-source hit, and 15% context traceability. Extracted-evidence citation integrity remains a separate diagnostic and validates source IDs, exact citation rendering, nonempty passage text, and offsets; it does not claim semantic entailment. When the local API is available, final answer synthesis is scored separately by `benchmarks.synthesize_answers`.

## Aggregate

| Mode | Fact recall | Fact-context precision | Preferred source | Evidence citation integrity | Context traceability | Cited fact recall | Readiness /100 | Mean latency s | Errors |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| raw_searxng | 0.7083 | 0.2833 | 0.6667 | 0.0000 | 1.0000 | 0.0000 | 68.21 | 0.00 | 0 |
| adaptive_hybrid | 1.0000 | 0.3599 | 0.6667 | 1.0000 | 1.0000 | 1.0000 | 85.40 | 2.62 | 0 |

## Per question

| Question | Mode | Fact recall | Fact-context precision | Preferred source | Evidence citation integrity | Context traceability | Readiness /100 | Latency s | Error |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| aq02 | adaptive_hybrid | 1.00 | 0.57 | 1 | 1.00 | 1.00 | 93.50 | 6.25 | — |
| aq02 | raw_searxng | 0.75 | 0.30 | 1 | 0.00 | 1.00 | 75.75 | 0.00 | — |
| aq02 | raw_searxng | 0.75 | 0.30 | 1 | 0.00 | 1.00 | 75.75 | 0.00 | — |
| aq02 | adaptive_hybrid | 1.00 | 0.57 | 1 | 1.00 | 1.00 | 93.50 | 3.62 | — |
| aq02 | adaptive_hybrid | 1.00 | 0.57 | 1 | 1.00 | 1.00 | 93.50 | 0.74 | — |
| aq02 | raw_searxng | 0.75 | 0.30 | 1 | 0.00 | 1.00 | 75.75 | 0.00 | — |
| aq05 | raw_searxng | 1.00 | 0.20 | 1 | 0.00 | 1.00 | 88.00 | 0.00 | — |
| aq05 | adaptive_hybrid | 1.00 | 0.24 | 1 | 1.00 | 1.00 | 88.53 | 6.91 | — |
| aq05 | adaptive_hybrid | 1.00 | 0.24 | 1 | 1.00 | 1.00 | 88.53 | 6.61 | — |
| aq05 | raw_searxng | 1.00 | 0.20 | 1 | 0.00 | 1.00 | 88.00 | 0.00 | — |
| aq05 | raw_searxng | 1.00 | 0.20 | 1 | 0.00 | 1.00 | 88.00 | 0.00 | — |
| aq05 | adaptive_hybrid | 1.00 | 0.24 | 1 | 1.00 | 1.00 | 88.53 | 6.60 | — |
| aq04 | adaptive_hybrid | 1.00 | 0.43 | 1 | 1.00 | 1.00 | 91.50 | 0.77 | — |
| aq04 | raw_searxng | 1.00 | 0.40 | 1 | 0.00 | 1.00 | 91.00 | 0.00 | — |
| aq04 | raw_searxng | 1.00 | 0.40 | 1 | 0.00 | 1.00 | 91.00 | 0.00 | — |
| aq04 | adaptive_hybrid | 1.00 | 0.43 | 1 | 1.00 | 1.00 | 91.50 | 0.65 | — |
| aq04 | adaptive_hybrid | 1.00 | 0.43 | 1 | 1.00 | 1.00 | 91.50 | 0.59 | — |
| aq04 | raw_searxng | 1.00 | 0.40 | 1 | 0.00 | 1.00 | 91.00 | 0.00 | — |
| aq03 | raw_searxng | 1.00 | 0.70 | 0 | 0.00 | 1.00 | 80.50 | 0.00 | — |
| aq03 | adaptive_hybrid | 1.00 | 0.73 | 0 | 1.00 | 1.00 | 81.00 | 0.75 | — |
| aq03 | adaptive_hybrid | 1.00 | 0.73 | 0 | 1.00 | 1.00 | 81.00 | 0.75 | — |
| aq03 | raw_searxng | 1.00 | 0.70 | 0 | 0.00 | 1.00 | 80.50 | 0.00 | — |
| aq03 | raw_searxng | 1.00 | 0.70 | 0 | 0.00 | 1.00 | 80.50 | 0.00 | — |
| aq03 | adaptive_hybrid | 1.00 | 0.73 | 0 | 1.00 | 1.00 | 81.00 | 0.73 | — |
| aq06 | adaptive_hybrid | 1.00 | 0.09 | 1 | 1.00 | 1.00 | 86.36 | 3.58 | — |
| aq06 | raw_searxng | 0.50 | 0.10 | 1 | 0.00 | 1.00 | 59.00 | 0.00 | — |
| aq06 | raw_searxng | 0.50 | 0.10 | 1 | 0.00 | 1.00 | 59.00 | 0.00 | — |
| aq06 | adaptive_hybrid | 1.00 | 0.09 | 1 | 1.00 | 1.00 | 86.36 | 3.86 | — |
| aq06 | adaptive_hybrid | 1.00 | 0.09 | 1 | 1.00 | 1.00 | 86.36 | 3.72 | — |
| aq06 | raw_searxng | 0.50 | 0.10 | 1 | 0.00 | 1.00 | 59.00 | 0.00 | — |
| aq01 | raw_searxng | 0.00 | 0.00 | 0 | 0.00 | 1.00 | 15.00 | 0.00 | — |
| aq01 | adaptive_hybrid | 1.00 | 0.10 | 0 | 1.00 | 1.00 | 71.50 | 0.34 | — |
| aq01 | adaptive_hybrid | 1.00 | 0.10 | 0 | 1.00 | 1.00 | 71.50 | 0.30 | — |
| aq01 | raw_searxng | 0.00 | 0.00 | 0 | 0.00 | 1.00 | 15.00 | 0.00 | — |
| aq01 | raw_searxng | 0.00 | 0.00 | 0 | 0.00 | 1.00 | 15.00 | 0.00 | — |
| aq01 | adaptive_hybrid | 1.00 | 0.10 | 0 | 1.00 | 1.00 | 71.50 | 0.35 | — |

Full assertion hits, excerpts, source metadata, and failures are written to the local generated artifact `latest-answer-quality-raw.json`, which is intentionally ignored by Git.
