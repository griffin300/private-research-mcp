# Evaluation

The benchmark contains 50 questions across factual, current/versioned software, comparisons, errors/issues, science, contradictions, freshness, obscure/multi-part topics, primary sources, duplicates, security/privacy, and unanswerable cases.

Run:

```powershell
.\scripts\run-benchmark.ps1
```

Each question runs against raw SearXNG, quick, standard, and deep modes. The report records latency, source/evidence counts, coverage, and errors. Raw packages permit calculation of fetch success, duplicates, primary-source rates, pages visited, cache behavior, and contradiction counts.

Relevance, citation support, freshness appropriateness, and unsupported-claim risk are not reliably inferred by this system evaluating itself. `latest-human-review.json` contains null fields for a reviewer; no score is fabricated. A valid release report must include the privacy-test result and disclose engine/CAPTCHA outages.

