# Final external benchmark summary

Six in-sample development questions, three repetitions, identical frozen exact-query snapshots, and the same local model for both systems. This is a regression suite, not proof of universal superiority.

| Measure | Raw SearXNG | Final private research tool | Difference |
|---|---:|---:|---:|
| Answer quality | 79.44 | 96.19 | +16.75 points / +21.1% relative |
| Retrieval readiness | 83.21 | 91.62 | +8.41 points / +10.1% relative |
| Fact recall | 83.33% | 96.30% | +12.97 points |
| Cited-context fact recall | 70.83% | 96.30% | +25.47 points |
| Citation precision | 94.44% | 99.31% | +4.87 points |
| Availability | 100% | 100% | tied |
| First-run total time | 17.91 s | 59.56 s | quality path is slower |
| Later-run total time | 18.49 s | 26.24 s | +7.75 s |

The tool wins this suite on answer quality, retrieval readiness, fact recall, grounding, and citation precision. Raw SearXNG remains faster, and it can tie or win individual simple snippet-rich questions. Results do not establish performance against unrelated commercial research products because those systems were not run in this paired harness.
