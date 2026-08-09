# Qwen 3.6 27B release A/B

Model: `qwen3.6-27b-uncensored-hauhaucs-aggressive` (Q4_K_P). Temperature: 0.
The model was loaded with a 23,296-token context and one prediction slot. Both systems received
the same frozen research packages and a 9,000-character response ceiling. A/B order alternated
between repetitions.

## Full release comparison

Six factual question types were answered twice per system (24 answers total). The completed
answers were deterministically rescored after the WAL matcher was corrected to recognize
semantically equivalent `n readers + 1 writer` wording. No model answer was edited. Final-release
contexts were reconstructed deterministically; the affected WAL case was then regenerated in the
targeted check below.

| System | Quality /100 | Fact recall | Grounded recall | Citation precision | Claim citation coverage | Mean context chars | Errors | Recovered retries |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Old renderer (`9bb7d9b`) | 98.89 | 1.0000 | 0.9444 | 1.0000 | 1.0000 | 8,893 | 0 | 0 |
| Final release | 100.00 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 8,940 | 0 | 0 |

The measured gain is **1.11 quality points** (about **1.12% relative**) and **5.56 grounded-recall
points**. Five of six questions were already tied at 100; the remaining gain came from the
multi-part SQLite WAL case.

| Question | Old | Final |
|---|---:|---:|
| MCP production transport | 100.00 | 100.00 |
| RFC 1918 blocks | 100.00 | 100.00 |
| HTTP 429 | 100.00 | 100.00 |
| SQLite WAL concurrency | 93.33 | 100.00 |
| curl SOCKS hostname resolution | 100.00 | 100.00 |
| Python 3.12.0 release date | 100.00 | 100.00 |

## Isolated final-pass check

The affected WAL case was rerun twice against the immediately preceding release (`aa1919d`).
Both sides used the same authority-selected evidence; only same-page snippet handling differed.

| Metric | Previous release | Final pass | Change |
|---|---:|---:|---:|
| Quality /100 | 100.00 | 100.00 | At score ceiling |
| Grounded recall | 1.0000 | 1.0000 | At score ceiling |
| Context characters | 8,968 | 8,874 | -1.0% |
| Mean answer words | 75 | 47 | -37.3% |
| Official SQLite concurrency citation used | 0/2 | 2/2 | +2 answers |
| Terminal errors / recovered retries | 0 / 0 | 0 / 0 | No change |

The final pass therefore improved source provenance and token efficiency on the observed failure
case, but it did **not** produce an additional composite-score gain because the preceding release
already reached 100 after the benchmark matcher was corrected.

## Limitations

This is a frozen-context presentation/selection A/B, not an end-to-end web retrieval benchmark and
not a comparison with raw SearXNG. Six short factual questions create a strong ceiling effect. The
single-slot configuration removed local LM Studio contention seen with four prediction slots, but
generation-time differences from the two-answer targeted check are too small and variable to
generalize. These figures support this release decision; they do not prove universal superiority.
