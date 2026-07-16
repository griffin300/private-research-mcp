# Paired gold-fact answer-quality benchmark

Questions: 6. Repetitions: 3. Seed: 20260714. Headline systems: raw SearXNG and quality-first adaptive hybrid.

This is a deterministic **answer-readiness** benchmark, not an LLM-as-judge score. The harness freezes one exact-query top-10 snapshot per question and supplies it to both systems; the hybrid adds query expansion, safe page extraction, source selection, and evidence ranking. Run order alternates to reduce order bias. Each question has hand-authored expected facts expressed as transparent regex alternatives plus preferred primary-source domains. Post-snapshot latency isolates each system's added work; end-to-end retrieval latency adds the measured shared SearXNG snapshot time back to both systems.

The composite is: 55% gold-fact recall, 15% fact-bearing-context precision, 15% preferred-source hit, and 15% context traceability. Extracted-evidence citation integrity remains a separate diagnostic and validates source IDs, exact citation rendering, nonempty passage text, and offsets; it does not claim semantic entailment. When the local API is available, final answer synthesis is scored separately by `benchmarks.synthesize_answers`.

## Aggregate

| Mode | Fact recall | Fact-context precision | Preferred source | Evidence citation integrity | Context traceability | Cited fact recall | Readiness /100 | Post-snapshot s | End-to-end retrieval s | Errors |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| raw_searxng | 0.9583 | 0.5333 | 0.5000 | 0.0000 | 1.0000 | 0.0000 | 83.21 | 0.00 | 10.72 | 0 |
| adaptive_hybrid | 1.0000 | 0.6080 | 0.8333 | 1.0000 | 1.0000 | 1.0000 | 91.62 | 12.29 | 23.01 | 0 |

## First/later repeat retrieval profile

"First repeat" is the first hybrid retrieval for each frozen question snapshot; later
repeats reuse the process-local search/page cache. Estimated end-to-end time adds the
measured shared exact-snapshot lookup to each system so the raw baseline is not given a
free search. This table avoids presenting their mixture as a pure cold or warm latency.

| Mode | First-repeat post-snapshot s | Later-repeat post-snapshot s | First-repeat estimated end-to-end s | Later-repeat estimated end-to-end s |
|---|---:|---:|---:|---:|
| raw_searxng | 0.00 | 0.00 | 10.72 | 10.72 |
| adaptive_hybrid | 33.79 | 1.54 | 44.51 | 12.26 |

## Per question

| Question | Mode | Fact recall | Fact-context precision | Preferred source | Evidence citation integrity | Context traceability | Readiness /100 | Post-snapshot s | End-to-end retrieval s | Error |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| aq02 | adaptive_hybrid | 1.00 | 0.89 | 1 | 1.00 | 1.00 | 98.33 | 17.96 | 33.05 | — |
| aq02 | raw_searxng | 0.75 | 0.90 | 1 | 0.00 | 1.00 | 84.75 | 0.00 | 15.10 | — |
| aq02 | raw_searxng | 0.75 | 0.90 | 1 | 0.00 | 1.00 | 84.75 | 0.00 | 15.10 | — |
| aq02 | adaptive_hybrid | 1.00 | 0.89 | 1 | 1.00 | 1.00 | 98.33 | 0.61 | 15.71 | — |
| aq02 | adaptive_hybrid | 1.00 | 0.89 | 1 | 1.00 | 1.00 | 98.33 | 0.69 | 15.78 | — |
| aq02 | raw_searxng | 0.75 | 0.90 | 1 | 0.00 | 1.00 | 84.75 | 0.00 | 15.10 | — |
| aq05 | raw_searxng | 1.00 | 0.50 | 0 | 0.00 | 1.00 | 77.50 | 0.00 | 15.03 | — |
| aq05 | adaptive_hybrid | 1.00 | 0.56 | 0 | 1.00 | 1.00 | 78.33 | 79.41 | 94.44 | — |
| aq05 | adaptive_hybrid | 1.00 | 0.56 | 0 | 1.00 | 1.00 | 78.33 | 6.91 | 21.94 | — |
| aq05 | raw_searxng | 1.00 | 0.50 | 0 | 0.00 | 1.00 | 77.50 | 0.00 | 15.03 | — |
| aq05 | raw_searxng | 1.00 | 0.50 | 0 | 0.00 | 1.00 | 77.50 | 0.00 | 15.03 | — |
| aq05 | adaptive_hybrid | 1.00 | 0.56 | 0 | 1.00 | 1.00 | 78.33 | 0.53 | 15.56 | — |
| aq04 | adaptive_hybrid | 1.00 | 0.61 | 1 | 1.00 | 1.00 | 94.17 | 35.08 | 37.10 | — |
| aq04 | raw_searxng | 1.00 | 0.70 | 1 | 0.00 | 1.00 | 95.50 | 0.00 | 2.02 | — |
| aq04 | raw_searxng | 1.00 | 0.70 | 1 | 0.00 | 1.00 | 95.50 | 0.00 | 2.02 | — |
| aq04 | adaptive_hybrid | 1.00 | 0.61 | 1 | 1.00 | 1.00 | 94.17 | 2.44 | 4.46 | — |
| aq04 | adaptive_hybrid | 1.00 | 0.61 | 1 | 1.00 | 1.00 | 94.17 | 0.95 | 2.97 | — |
| aq04 | raw_searxng | 1.00 | 0.70 | 1 | 0.00 | 1.00 | 95.50 | 0.00 | 2.02 | — |
| aq03 | raw_searxng | 1.00 | 0.70 | 0 | 0.00 | 1.00 | 80.50 | 0.00 | 15.03 | — |
| aq03 | adaptive_hybrid | 1.00 | 0.78 | 1 | 1.00 | 1.00 | 96.67 | 29.00 | 44.04 | — |
| aq03 | adaptive_hybrid | 1.00 | 0.78 | 1 | 1.00 | 1.00 | 96.67 | 2.22 | 17.25 | — |
| aq03 | raw_searxng | 1.00 | 0.70 | 0 | 0.00 | 1.00 | 80.50 | 0.00 | 15.03 | — |
| aq03 | raw_searxng | 1.00 | 0.70 | 0 | 0.00 | 1.00 | 80.50 | 0.00 | 15.03 | — |
| aq03 | adaptive_hybrid | 1.00 | 0.78 | 1 | 1.00 | 1.00 | 96.67 | 0.40 | 15.44 | — |
| aq06 | adaptive_hybrid | 1.00 | 0.50 | 1 | 1.00 | 1.00 | 92.50 | 28.31 | 30.42 | — |
| aq06 | raw_searxng | 1.00 | 0.30 | 1 | 0.00 | 1.00 | 89.50 | 0.00 | 2.11 | — |
| aq06 | raw_searxng | 1.00 | 0.30 | 1 | 0.00 | 1.00 | 89.50 | 0.00 | 2.11 | — |
| aq06 | adaptive_hybrid | 1.00 | 0.56 | 1 | 1.00 | 1.00 | 93.33 | 2.39 | 4.50 | — |
| aq06 | adaptive_hybrid | 1.00 | 0.56 | 1 | 1.00 | 1.00 | 93.33 | 0.39 | 2.51 | — |
| aq06 | raw_searxng | 1.00 | 0.30 | 1 | 0.00 | 1.00 | 89.50 | 0.00 | 2.11 | — |
| aq01 | raw_searxng | 1.00 | 0.10 | 0 | 0.00 | 1.00 | 71.50 | 0.00 | 15.03 | — |
| aq01 | adaptive_hybrid | 1.00 | 0.28 | 1 | 1.00 | 1.00 | 89.17 | 12.98 | 28.00 | — |
| aq01 | adaptive_hybrid | 1.00 | 0.28 | 1 | 1.00 | 1.00 | 89.17 | 0.46 | 15.49 | — |
| aq01 | raw_searxng | 1.00 | 0.10 | 0 | 0.00 | 1.00 | 71.50 | 0.00 | 15.03 | — |
| aq01 | raw_searxng | 1.00 | 0.10 | 0 | 0.00 | 1.00 | 71.50 | 0.00 | 15.03 | — |
| aq01 | adaptive_hybrid | 1.00 | 0.28 | 1 | 1.00 | 1.00 | 89.17 | 0.44 | 15.46 | — |

Full assertion hits, excerpts, source metadata, and failures are written to the local generated artifact `latest-answer-quality-raw.json`, which is intentionally ignored by Git.
