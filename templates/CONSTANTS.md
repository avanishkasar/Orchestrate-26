# Constants

Every number in the code that changes behaviour gets a row here. Provenance:
**MEASURED** (sample/eval result, cite the run), **SPEC** (problem statement, quote it),
**STANDARD** (vendor limit or convention, link it), **JUDGEMENT** (my call, give the reason).

| Constant | Value | Where (file:line) | Provenance | Evidence / reason |
|---|---|---|---|---|
| `max_steps` | 8 | | JUDGEMENT | |
| `budget_tokens` | 60000 | | MEASURED | p95 tokens/row on samples = … |
| `DEFAULT_MAX_EDGE_PX` | 1568 | okit/perception/image.py | STANDARD | vendor vision limit |
| injection `DEFAULT_THRESHOLD` | 0.4 | okit/safety/injection.py | MEASURED | precision/recall on samples = … |
| confidence band | 0.78–0.91 | | MEASURED | min/max of sample `confidence` |
