# Locally synthesized answer-quality benchmark

Model: `qwen3.6-35b-a3b-uncensored-hauhaucs-aggressive`. The same local model synthesized an answer for both systems. Questions: 6. Repetitions: 3. Answer runs: 36.

The deterministic composite is 55% gold-fact recall, 20% gold facts sharing a claim unit with a valid supplied citation, 15% citation precision, and 10% claim citation coverage. Citation precision and coverage credit is gated in proportion to gold-fact recall, so citation-only non-answers earn no points. Gold facts are hand-authored regex alternatives. The uncited-claim measure is a transparent formatting proxy, not semantic entailment and not an LLM-as-judge score.

## Aggregate

| Mode | Answer fact recall | Grounded fact recall | Citation precision | Claim citation coverage | Availability | End-to-end quality /100 | Quality when available /100 | Mean synthesis s | Total pipeline s | Errors |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| raw_searxng | 0.6667 | 0.5278 | 0.7407 | 0.7074 | 1.0000 | 61.24 | 61.24 | 6.12 | 10.12 | 0 |
| adaptive_hybrid | 0.6667 | 0.6667 | 0.8333 | 0.7167 | 1.0000 | 66.33 | 66.33 | 15.84 | 41.42 | 0 |

## Per question

| Question | Mode | Answer fact recall | Grounded fact recall | Citation precision | Claim citation coverage | Quality /100 | Synthesis s | Total pipeline s | Error |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| aq02 | adaptive_hybrid | 1.00 | 1.00 | 1.00 | 0.80 | 98.00 | 27.69 | 71.28 | — |
| aq02 | raw_searxng | 1.00 | 1.00 | 1.00 | 0.80 | 98.00 | 10.62 | 17.39 | — |
| aq02 | raw_searxng | 1.00 | 1.00 | 1.00 | 0.80 | 98.00 | 12.59 | 19.36 | — |
| aq02 | adaptive_hybrid | 1.00 | 1.00 | 1.00 | 0.80 | 98.00 | 23.92 | 32.75 | — |
| aq02 | adaptive_hybrid | 1.00 | 1.00 | 1.00 | 0.80 | 98.00 | 22.75 | 30.36 | — |
| aq02 | raw_searxng | 1.00 | 1.00 | 1.00 | 0.80 | 98.00 | 13.17 | 19.94 | — |
| aq05 | raw_searxng | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 6.80 | 10.69 | — |
| aq05 | adaptive_hybrid | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 15.09 | 160.75 | — |
| aq05 | adaptive_hybrid | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 13.22 | 25.69 | — |
| aq05 | raw_searxng | 1.00 | 1.00 | 0.67 | 1.00 | 95.00 | 5.61 | 9.50 | — |
| aq05 | raw_searxng | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 6.41 | 10.30 | — |
| aq05 | adaptive_hybrid | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 13.47 | 19.92 | — |
| aq04 | adaptive_hybrid | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 12.55 | 32.55 | — |
| aq04 | raw_searxng | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 4.49 | 8.50 | — |
| aq04 | raw_searxng | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 4.88 | 8.89 | — |
| aq04 | adaptive_hybrid | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 13.56 | 19.87 | — |
| aq04 | adaptive_hybrid | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 12.34 | 92.17 | — |
| aq04 | raw_searxng | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 6.89 | 10.90 | — |
| aq03 | raw_searxng | 1.00 | 0.50 | 0.33 | 0.33 | 73.33 | 6.51 | 9.98 | — |
| aq03 | adaptive_hybrid | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 28.59 | 57.88 | — |
| aq03 | adaptive_hybrid | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 12.52 | 16.80 | — |
| aq03 | raw_searxng | 1.00 | 0.00 | 0.67 | 0.50 | 70.00 | 6.08 | 9.55 | — |
| aq03 | raw_searxng | 1.00 | 0.00 | 0.67 | 0.50 | 70.00 | 5.19 | 8.66 | — |
| aq03 | adaptive_hybrid | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 18.53 | 22.78 | — |
| aq06 | adaptive_hybrid | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 12.42 | 36.85 | — |
| aq06 | raw_searxng | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 4.02 | 7.12 | — |
| aq06 | raw_searxng | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 3.50 | 6.61 | — |
| aq06 | adaptive_hybrid | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 13.11 | 18.65 | — |
| aq06 | adaptive_hybrid | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 11.67 | 15.37 | — |
| aq06 | raw_searxng | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 3.94 | 7.04 | — |
| aq01 | raw_searxng | 0.00 | 0.00 | 1.00 | 1.00 | 0.00 | 3.22 | 5.97 | — |
| aq01 | adaptive_hybrid | 0.00 | 0.00 | 1.00 | 0.50 | 0.00 | 10.03 | 61.55 | — |
| aq01 | adaptive_hybrid | 0.00 | 0.00 | 1.00 | 0.50 | 0.00 | 10.97 | 14.33 | — |
| aq01 | raw_searxng | 0.00 | 0.00 | 1.00 | 1.00 | 0.00 | 3.61 | 6.36 | — |
| aq01 | raw_searxng | 0.00 | 0.00 | 1.00 | 1.00 | 0.00 | 2.56 | 5.32 | — |
| aq01 | adaptive_hybrid | 0.00 | 0.00 | 1.00 | 0.50 | 0.00 | 12.62 | 15.94 | — |

Full generated answers, assertions, claim units, citations, retrieval packages, and errors are written to the local generated artifact `latest-synthesized-answers.json`, which is intentionally ignored by Git.
