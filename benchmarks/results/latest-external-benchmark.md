# Private Research MCP vs. raw SearXNG

Controlled local benchmark, 2026-07-14. Six questions, three repetitions per system, 36 generated answers total. Both systems received the same frozen exact-query top-10 SearXNG snapshot and used the same local 35B answer model at temperature 0. The research system retained that raw context and added private expansion, page extraction, ranking, and cited evidence.

## Headline results

| Quality measure | Raw SearXNG | Private Research MCP | Gain |
|---|---:|---:|---:|
| Final answer quality | 61.60 / 100 | **99.48 / 100** | **+37.88 points (+61.5%)** |
| Answer fact recall | 63.89% | **100.00%** | **+36.11 points** |
| Grounded fact recall | 63.89% | **100.00%** | **+36.11 points** |
| Citation precision | 90.28% | **100.00%** | **+9.72 points** |
| Answer availability | 100.00% | **100.00%** | No regression |
| Retrieval readiness | 68.21 / 100 | **85.40 / 100** | **+17.19 points (+25.2%)** |
| Retrieval fact recall | 70.83% | **100.00%** | **+29.17 points** |

## Per-question final answer quality

| Workload | Raw SearXNG | Private Research MCP | Result |
|---|---:|---:|---|
| Production protocol recommendation | 0.00 | **98.89** | Win |
| Standard plus four required facts | 81.67 | **98.00** | Win |
| HTTP definition | 91.67 | **100.00** | Win |
| Database concurrency explanation | 96.25 | **100.00** | Win |
| Constrained proxy comparison | **100.00** | **100.00** | Tie at ceiling |
| Historical release date | 0.00 | **100.00** | Win |

**Outcome: five wins, one tie, zero losses.**

The scoring is deterministic and auditable, not an LLM-as-judge rating. This six-question technical suite is a regression benchmark, not proof that any generative system will outperform raw search on every possible real-world query. The versioned harness and the two detailed reports document the formulas; full-run JSON artifacts are generated locally and intentionally ignored by Git.
