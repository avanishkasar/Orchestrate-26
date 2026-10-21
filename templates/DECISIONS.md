# Decisions

One entry per non-obvious choice. The interview asks "why X and not Y"; the answer lives here.

## D1: <title>
- **Date/time (IST):**
- **Decision:**
- **Options considered:** A / B / C
- **Evidence:** numbers, run ids, sample rows
- **Rejected because:**
- **Where it stops being true:**

## Pre-event tooling disclosure
`okit/` (LLM client, disk cache, usage ledger, rate limiter, checkpoint runner, image/audio
loaders, injection heuristic, bounded agent loop, eval scorer, output validator, zip builder)
was written by me before the event as generic, domain-agnostic tooling. All domain logic,
prompts, schemas, rules and templates in this submission were written during the event.
