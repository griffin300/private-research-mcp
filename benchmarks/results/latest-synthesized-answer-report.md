# Locally synthesized answer-quality benchmark

Model: `qwen3.6-35b-a3b-uncensored-hauhaucs-aggressive`. The same local model synthesized an answer for both systems. Questions: 6. Repetitions: 3. Answer runs: 36.

The deterministic composite is 55% gold-fact recall, 20% gold facts sharing a claim unit with a valid supplied citation, 15% citation precision, and 10% claim citation coverage. Citation precision and coverage credit is gated in proportion to gold-fact recall, so citation-only non-answers earn no points. Gold facts are hand-authored regex alternatives. The uncited-claim measure is a transparent formatting proxy, not semantic entailment and not an LLM-as-judge score.

## Aggregate

| Mode | Answer fact recall | Grounded fact recall | Citation precision | Claim citation coverage | Availability | End-to-end quality /100 | Quality when available /100 | Mean synthesis s | Errors |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| raw_searxng | 0.6389 | 0.6389 | 0.9028 | 0.8278 | 1.0000 | 61.60 | 61.60 | 5.02 | 0 |
| adaptive_hybrid | 1.0000 | 1.0000 | 1.0000 | 0.9482 | 1.0000 | 99.48 | 99.48 | 11.73 | 0 |

## Per question

| Question | Mode | Answer fact recall | Grounded fact recall | Citation precision | Claim citation coverage | Quality /100 | Synthesis s | Error |
|---|---|---:|---:|---:|---:|---:|---:|---|
| aq02 | adaptive_hybrid | 1.00 | 1.00 | 1.00 | 0.80 | 98.00 | 17.97 | — |
| aq02 | raw_searxng | 1.00 | 1.00 | 1.00 | 0.80 | 98.00 | 10.89 | — |
| aq02 | raw_searxng | 0.75 | 0.75 | 1.00 | 0.80 | 73.50 | 8.83 | — |
| aq02 | adaptive_hybrid | 1.00 | 1.00 | 1.00 | 0.80 | 98.00 | 18.08 | — |
| aq02 | adaptive_hybrid | 1.00 | 1.00 | 1.00 | 0.80 | 98.00 | 17.22 | — |
| aq02 | raw_searxng | 0.75 | 0.75 | 1.00 | 0.80 | 73.50 | 9.64 | — |
| aq05 | raw_searxng | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 3.77 | — |
| aq05 | adaptive_hybrid | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 11.31 | — |
| aq05 | adaptive_hybrid | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 10.56 | — |
| aq05 | raw_searxng | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 4.17 | — |
| aq05 | raw_searxng | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 3.22 | — |
| aq05 | adaptive_hybrid | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 11.23 | — |
| aq04 | adaptive_hybrid | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 10.75 | — |
| aq04 | raw_searxng | 1.00 | 1.00 | 0.75 | 1.00 | 96.25 | 4.17 | — |
| aq04 | raw_searxng | 1.00 | 1.00 | 0.75 | 1.00 | 96.25 | 3.81 | — |
| aq04 | adaptive_hybrid | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 11.00 | — |
| aq04 | adaptive_hybrid | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 10.03 | — |
| aq04 | raw_searxng | 1.00 | 1.00 | 0.75 | 1.00 | 96.25 | 4.53 | — |
| aq03 | raw_searxng | 1.00 | 1.00 | 0.67 | 0.67 | 91.67 | 4.44 | — |
| aq03 | adaptive_hybrid | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 12.83 | — |
| aq03 | adaptive_hybrid | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 10.84 | — |
| aq03 | raw_searxng | 1.00 | 1.00 | 0.67 | 0.67 | 91.67 | 4.92 | — |
| aq03 | raw_searxng | 1.00 | 1.00 | 0.67 | 0.67 | 91.67 | 4.03 | — |
| aq03 | adaptive_hybrid | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 12.72 | — |
| aq06 | adaptive_hybrid | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 9.16 | — |
| aq06 | raw_searxng | 0.00 | 0.00 | 1.00 | 1.00 | 0.00 | 3.33 | — |
| aq06 | raw_searxng | 0.00 | 0.00 | 1.00 | 1.00 | 0.00 | 2.88 | — |
| aq06 | adaptive_hybrid | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 9.36 | — |
| aq06 | adaptive_hybrid | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 8.41 | — |
| aq06 | raw_searxng | 0.00 | 0.00 | 1.00 | 1.00 | 0.00 | 3.61 | — |
| aq01 | raw_searxng | 0.00 | 0.00 | 1.00 | 0.50 | 0.00 | 5.19 | — |
| aq01 | adaptive_hybrid | 1.00 | 1.00 | 1.00 | 0.67 | 96.67 | 10.98 | — |
| aq01 | adaptive_hybrid | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 8.73 | — |
| aq01 | raw_searxng | 0.00 | 0.00 | 1.00 | 0.50 | 0.00 | 4.89 | — |
| aq01 | raw_searxng | 0.00 | 0.00 | 1.00 | 0.50 | 0.00 | 4.11 | — |
| aq01 | adaptive_hybrid | 1.00 | 1.00 | 1.00 | 1.00 | 100.00 | 9.97 | — |

Full generated answers, assertions, claim units, citations, retrieval packages, and errors are written to the local generated artifact `latest-synthesized-answers.json`, which is intentionally ignored by Git.
