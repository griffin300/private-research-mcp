# Evaluation

The benchmark contains 50 questions across factual, current/versioned software, comparisons, errors/issues, science, contradictions, freshness, obscure/multi-part topics, primary sources, duplicates, security/privacy, and unanswerable cases.

Run:

```powershell
.\scripts\run-benchmark.ps1
```

Each question runs against raw SearXNG, quick, standard, and deep modes. The report records latency, source/evidence counts, coverage, and errors. Raw packages permit calculation of fetch success, duplicates, primary-source rates, pages visited, cache behavior, and contradiction counts.

Relevance, citation support, freshness appropriateness, and unsupported-claim risk are not reliably inferred by this system evaluating itself. `latest-human-review.json` contains null fields for a reviewer; no score is fabricated. A valid release report must include the privacy-test result and disclose engine/CAPTCHA outages.

## Gold-fact answer readiness

Run `.\scripts\run-answer-quality.ps1` for the smaller deterministic suite. Its hand-authored assertions and accepted regex alternatives live in `benchmarks/answer_quality_questions.json`. The report separates measurable fact recall, fact-bearing-context precision, preferred-source presence, citation integrity, and cited-fact recall. The weighted readiness score is a declared retrieval/evidence heuristic, not a claim that an LLM produced a correct final answer.

When LM Studio's local API is available, the same script then asks the loaded non-embedding model to synthesize an answer from each mode's context. It scores answer-level gold-fact recall, gold facts accompanied by valid supplied citations, citation precision, and claim citation coverage. The scorer is deterministic and auditable; claim citation coverage is a formatting proxy and does not prove semantic entailment.

The synthesis benchmark caps each prompt at eight globally ranked evidence records and 12,000 context characters. It exposes compact labels such as `[E1]` to the model and records a deterministic map back to canonical `[source_id, evidence_id]` citations. This keeps prompts bounded and prevents the model from shortening canonical evidence identifiers.
