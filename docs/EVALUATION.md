# Evaluation

The benchmark contains 50 questions across factual, current/versioned software, comparisons, errors/issues, science, contradictions, freshness, obscure/multi-part topics, primary sources, duplicates, security/privacy, and unanswerable cases.

Run:

```powershell
.\scripts\run-benchmark.ps1
```

Each question runs against raw SearXNG, quick, standard, and deep modes. The report records latency, source/evidence counts, coverage, and errors. Raw packages permit calculation of fetch success, duplicates, primary-source rates, pages visited, cache behavior, and contradiction counts.

Relevance, citation support, freshness appropriateness, and unsupported-claim risk are not reliably inferred by this system evaluating itself. `latest-human-review.json` contains null fields for a reviewer; no score is fabricated. A valid release report must include the privacy-test result and disclose engine/CAPTCHA outages.

## Gold-fact answer readiness

Run `.\scripts\run-answer-quality.ps1` for the smaller deterministic suite. Its hand-authored assertions and accepted regex alternatives live in `benchmarks/answer_quality_questions.json`. The headline systems are raw SearXNG and the production adaptive hybrid; quick/standard/deep are internal controls, not separate products. The harness prefetches and freezes one exact-query top-10 snapshot per question, supplies that identical snapshot to both systems, runs three repetitions by default, and alternates system order with a logged seed. This removes the former raw-first throttling bias and isolates the value of additive expansion, extraction, and ranking. Reported latency begins after the shared snapshot and is therefore diagnostic, not an end-to-end search comparison.

The report separates measurable fact recall, fact-bearing-context precision, preferred-source presence, context traceability, extracted-evidence citation integrity, and cited-fact recall. Search snippets can earn traceability but cannot inflate offset-validated evidence integrity. The weighted readiness score is 55% fact recall, 15% fact-bearing-context precision, 15% preferred-source presence, and 15% context traceability. It is a declared retrieval heuristic, not a claim that an LLM produced a correct final answer.

When LM Studio's local API is available, the same script then asks the loaded non-embedding model to synthesize an answer from each system's context. It scores answer-level gold-fact recall, gold facts accompanied by valid supplied citations, citation precision, and claim citation coverage. The scorer is deterministic and auditable; claim citation coverage is a formatting proxy and does not prove semantic entailment.

The synthesis benchmark caps each prompt at 16,000 context characters. It reserves at most half for all 10 compact exact-query snippets and uses the remainder for up to eight globally ranked evidence records. It exposes `[S#]` labels for explicitly unverified search snippets and `[E#]` labels for extracted evidence, records deterministic maps to canonical citations, excludes redacted high-risk snippets, and tells the model to prefer `[E#]` when available.

The current gold suite has only six mostly technical fact questions. It is a regression test, not proof of superiority on all web research. A publishable claim should use a locked development/evaluation split with at least 32 questions across static facts, volatile facts, primary documentation, multi-hop synthesis, constrained comparisons, conflicting evidence, noisy SEO results, and unanswerable cases; three or more repetitions; paired confidence intervals; and per-category non-inferiority. No architecture can guarantee that a generative model will produce a better answer on every individual query.
