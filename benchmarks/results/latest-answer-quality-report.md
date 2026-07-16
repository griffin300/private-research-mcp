# Paired gold-fact answer-quality benchmark

Questions: 6. Repetitions: 3. Seed: 20260714. Headline systems: raw SearXNG and quality-first adaptive hybrid.

This is a deterministic **answer-readiness** benchmark, not an LLM-as-judge score. The harness freezes one exact-query top-10 snapshot per question and supplies it to both systems; the hybrid adds query expansion, safe page extraction, source selection, and evidence ranking. Run order alternates to reduce order bias. Each question has hand-authored expected facts expressed as transparent regex alternatives plus preferred primary-source domains. Post-snapshot latency isolates each system's added work; end-to-end retrieval latency adds the measured shared SearXNG snapshot time back to both systems.

The composite is: 55% gold-fact recall, 15% fact-bearing-context precision, 15% preferred-source hit, and 15% context traceability. Extracted-evidence citation integrity remains a separate diagnostic and validates source IDs, exact citation rendering, nonempty passage text, and offsets; it does not claim semantic entailment. When the local API is available, final answer synthesis is scored separately by `benchmarks.synthesize_answers`.

## Aggregate

| Mode | Fact recall | Fact-context precision | Preferred source | Evidence citation integrity | Context traceability | Cited fact recall | Readiness /100 | Post-snapshot s | End-to-end retrieval s | Errors |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| raw_searxng | 0.6250 | 0.4500 | 0.3333 | 0.0000 | 1.0000 | 0.0000 | 61.12 | 0.00 | 4.00 | 0 |
| adaptive_hybrid | 0.8333 | 0.4257 | 0.5000 | 1.0000 | 1.0000 | 0.8333 | 74.72 | 21.58 | 25.58 | 0 |

## Per question

| Question | Mode | Fact recall | Fact-context precision | Preferred source | Evidence citation integrity | Context traceability | Readiness /100 | Post-snapshot s | End-to-end retrieval s | Error |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| aq02 | adaptive_hybrid | 1.00 | 0.83 | 1 | 1.00 | 1.00 | 97.50 | 36.82 | 43.59 | — |
| aq02 | raw_searxng | 0.75 | 0.80 | 1 | 0.00 | 1.00 | 83.25 | 0.00 | 6.77 | — |
| aq02 | raw_searxng | 0.75 | 0.80 | 1 | 0.00 | 1.00 | 83.25 | 0.00 | 6.76 | — |
| aq02 | adaptive_hybrid | 1.00 | 0.83 | 1 | 1.00 | 1.00 | 97.50 | 2.06 | 8.83 | — |
| aq02 | adaptive_hybrid | 1.00 | 0.83 | 1 | 1.00 | 1.00 | 97.50 | 0.84 | 7.61 | — |
| aq02 | raw_searxng | 0.75 | 0.80 | 1 | 0.00 | 1.00 | 83.25 | 0.00 | 6.76 | — |
| aq05 | raw_searxng | 1.00 | 0.60 | 0 | 0.00 | 1.00 | 79.00 | 0.00 | 3.89 | — |
| aq05 | adaptive_hybrid | 1.00 | 0.47 | 1 | 1.00 | 1.00 | 92.06 | 141.77 | 145.66 | — |
| aq05 | adaptive_hybrid | 1.00 | 0.53 | 1 | 1.00 | 1.00 | 92.94 | 8.58 | 12.47 | — |
| aq05 | raw_searxng | 1.00 | 0.60 | 0 | 0.00 | 1.00 | 79.00 | 0.00 | 3.89 | — |
| aq05 | raw_searxng | 1.00 | 0.60 | 0 | 0.00 | 1.00 | 79.00 | 0.00 | 3.89 | — |
| aq05 | adaptive_hybrid | 1.00 | 0.53 | 1 | 1.00 | 1.00 | 92.94 | 2.56 | 6.45 | — |
| aq04 | adaptive_hybrid | 1.00 | 0.70 | 1 | 1.00 | 1.00 | 95.50 | 16.00 | 20.01 | — |
| aq04 | raw_searxng | 1.00 | 0.80 | 1 | 0.00 | 1.00 | 97.00 | 0.00 | 4.01 | — |
| aq04 | raw_searxng | 1.00 | 0.80 | 1 | 0.00 | 1.00 | 97.00 | 0.00 | 4.01 | — |
| aq04 | adaptive_hybrid | 1.00 | 0.67 | 1 | 1.00 | 1.00 | 95.00 | 2.30 | 6.31 | — |
| aq04 | adaptive_hybrid | 1.00 | 0.67 | 1 | 1.00 | 1.00 | 95.00 | 75.82 | 79.83 | — |
| aq04 | raw_searxng | 1.00 | 0.80 | 1 | 0.00 | 1.00 | 97.00 | 0.00 | 4.01 | — |
| aq03 | raw_searxng | 1.00 | 0.50 | 0 | 0.00 | 1.00 | 77.50 | 0.00 | 3.47 | — |
| aq03 | adaptive_hybrid | 1.00 | 0.50 | 0 | 1.00 | 1.00 | 77.50 | 25.82 | 29.29 | — |
| aq03 | adaptive_hybrid | 1.00 | 0.50 | 0 | 1.00 | 1.00 | 77.50 | 0.81 | 4.28 | — |
| aq03 | raw_searxng | 1.00 | 0.50 | 0 | 0.00 | 1.00 | 77.50 | 0.00 | 3.47 | — |
| aq03 | raw_searxng | 1.00 | 0.50 | 0 | 0.00 | 1.00 | 77.50 | 0.00 | 3.47 | — |
| aq03 | adaptive_hybrid | 1.00 | 0.50 | 0 | 1.00 | 1.00 | 77.50 | 0.78 | 4.25 | — |
| aq06 | adaptive_hybrid | 0.00 | 0.00 | 0 | 1.00 | 1.00 | 15.00 | 21.32 | 24.43 | — |
| aq06 | raw_searxng | 0.00 | 0.00 | 0 | 0.00 | 1.00 | 15.00 | 0.00 | 3.11 | — |
| aq06 | raw_searxng | 0.00 | 0.00 | 0 | 0.00 | 1.00 | 15.00 | 0.00 | 3.11 | — |
| aq06 | adaptive_hybrid | 0.00 | 0.00 | 0 | 1.00 | 1.00 | 15.00 | 2.44 | 5.54 | — |
| aq06 | adaptive_hybrid | 0.00 | 0.00 | 0 | 1.00 | 1.00 | 15.00 | 0.59 | 3.69 | — |
| aq06 | raw_searxng | 0.00 | 0.00 | 0 | 0.00 | 1.00 | 15.00 | 0.00 | 3.11 | — |
| aq01 | raw_searxng | 0.00 | 0.00 | 0 | 0.00 | 1.00 | 15.00 | 0.00 | 2.75 | — |
| aq01 | adaptive_hybrid | 1.00 | 0.03 | 0 | 1.00 | 1.00 | 70.50 | 48.77 | 51.52 | — |
| aq01 | adaptive_hybrid | 1.00 | 0.03 | 0 | 1.00 | 1.00 | 70.50 | 0.61 | 3.36 | — |
| aq01 | raw_searxng | 0.00 | 0.00 | 0 | 0.00 | 1.00 | 15.00 | 0.00 | 2.75 | — |
| aq01 | raw_searxng | 0.00 | 0.00 | 0 | 0.00 | 1.00 | 15.00 | 0.00 | 2.76 | — |
| aq01 | adaptive_hybrid | 1.00 | 0.03 | 0 | 1.00 | 1.00 | 70.50 | 0.56 | 3.32 | — |

Full assertion hits, excerpts, source metadata, and failures are written to the local generated artifact `latest-answer-quality-raw.json`, which is intentionally ignored by Git.
