# Locally synthesized answer-quality benchmark

Model: `qwen3.6-35b-a3b-uncensored-hauhaucs-aggressive`. The same local model synthesized an answer for both systems. Questions: 6. Repetitions: 3. Answer runs: 36.

The deterministic composite is 55% gold-fact recall, 20% cited-context fact recall, 15% citation precision, and 10% claim citation coverage. Cited-context fact recall requires the gold-fact regex both in the answer claim and in at least one supplied context cited by that claim; a merely valid but unrelated citation earns no grounding credit. Citation precision and coverage credit is gated in proportion to gold-fact recall, so citation-only non-answers earn no points. Gold facts are hand-authored regex alternatives. Cited-context matching and the uncited-claim measure are transparent lexical/formatting proxies, not semantic entailment or an LLM-as-judge score.

## Aggregate

| Mode | Answer fact recall | Cited-context fact recall | Citation precision | Claim citation coverage | Availability | End-to-end quality /100 | Quality when available /100 | Mean synthesis s | Total pipeline s | Errors |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| raw_searxng | 0.8333 | 0.7083 | 0.9444 | 0.9444 | 1.0000 | 79.44 | 79.44 | 7.58 | 18.30 | 0 |
| adaptive_hybrid | 0.9630 | 0.9630 | 0.9931 | 1.0000 | 1.0000 | 96.19 | 96.19 | 14.34 | 37.35 | 0 |

## First/later repeat pipeline profile

First-repeat retrieval is the first full retrieval for each frozen question; later
repeats may use process-local caches. Total pipeline time includes the shared exact-query
snapshot estimate, hybrid retrieval, and local answer generation.

| Mode | First-repeat synthesis s | Later-repeat synthesis s | First-repeat total s | Later-repeat total s |
|---|---:|---:|---:|---:|
| raw_searxng | 7.19 | 7.77 | 17.91 | 18.49 |
| adaptive_hybrid | 15.05 | 13.98 | 59.56 | 26.24 |

## Per question

| Question | Mode | Answer fact recall | Cited-context fact recall | Citation precision | Claim citation coverage | Quality /100 | Synthesis s | Total pipeline s | Error |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| aq02 | adaptive_hybrid | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 20.14 | 53.19 | — |
| aq02 | raw_searxng | 1.00 | 0.75 | 1.00 | 1.00 | 95.00 | 10.41 | 25.50 | — |
| aq02 | raw_searxng | 1.00 | 0.75 | 1.00 | 1.00 | 95.00 | 9.69 | 24.78 | — |
| aq02 | adaptive_hybrid | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 18.33 | 34.04 | — |
| aq02 | adaptive_hybrid | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 17.45 | 33.23 | — |
| aq02 | raw_searxng | 1.00 | 0.75 | 1.00 | 1.00 | 95.00 | 10.62 | 25.72 | — |
| aq05 | raw_searxng | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 6.91 | 21.94 | — |
| aq05 | adaptive_hybrid | 1.00 | 1.00 | 0.88 | 1.00 | 98.12 | 15.33 | 109.77 | — |
| aq05 | adaptive_hybrid | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 13.52 | 35.46 | — |
| aq05 | raw_searxng | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 7.12 | 22.16 | — |
| aq05 | raw_searxng | 1.00 | 0.00 | 0.00 | 0.00 | 55.00 | 6.14 | 21.17 | — |
| aq05 | adaptive_hybrid | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 14.98 | 30.54 | — |
| aq04 | adaptive_hybrid | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 13.00 | 50.10 | — |
| aq04 | raw_searxng | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 5.86 | 7.88 | — |
| aq04 | raw_searxng | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 3.47 | 5.49 | — |
| aq04 | adaptive_hybrid | 0.67 | 0.67 | 1.00 | 1.00 | 66.67 | 12.41 | 16.87 | — |
| aq04 | adaptive_hybrid | 0.67 | 0.67 | 1.00 | 1.00 | 66.67 | 11.12 | 14.09 | — |
| aq04 | raw_searxng | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 4.50 | 6.52 | — |
| aq03 | raw_searxng | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 9.86 | 24.89 | — |
| aq03 | adaptive_hybrid | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 14.39 | 58.43 | — |
| aq03 | adaptive_hybrid | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 13.20 | 30.46 | — |
| aq03 | raw_searxng | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 9.28 | 24.32 | — |
| aq03 | raw_searxng | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 8.45 | 23.49 | — |
| aq03 | adaptive_hybrid | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 13.75 | 29.19 | — |
| aq06 | adaptive_hybrid | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 17.09 | 47.51 | — |
| aq06 | raw_searxng | 1.00 | 0.50 | 1.00 | 1.00 | 90.00 | 6.28 | 8.39 | — |
| aq06 | raw_searxng | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 15.83 | 17.94 | — |
| aq06 | adaptive_hybrid | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 17.47 | 21.97 | — |
| aq06 | adaptive_hybrid | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 16.22 | 18.73 | — |
| aq06 | raw_searxng | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 12.44 | 14.55 | — |
| aq01 | raw_searxng | 0.00 | 0.00 | 1.00 | 1.00 | 0.00 | 3.83 | 18.86 | — |
| aq01 | adaptive_hybrid | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 10.33 | 38.33 | — |
| aq01 | adaptive_hybrid | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 8.94 | 24.43 | — |
| aq01 | raw_searxng | 0.00 | 0.00 | 1.00 | 1.00 | 0.00 | 3.28 | 18.31 | — |
| aq01 | raw_searxng | 0.00 | 0.00 | 1.00 | 1.00 | 0.00 | 2.42 | 17.45 | — |
| aq01 | adaptive_hybrid | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 10.42 | 25.89 | — |

Full generated answers, assertions, claim units, citations, retrieval packages, and errors are written to the local generated artifact `latest-synthesized-answers.json`, which is intentionally ignored by Git.
