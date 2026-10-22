# Orchestrate-26 prep kit (`okit`)

Generic, domain-agnostic tooling for a 24-hour agent build (HackerRank Orchestrate, Oct 24–25 2026).
It contains **no domain logic**. The point is to spend event hours on the problem, not on plumbing,
and to have every piece tested before the clock starts.

| Module | What it does |
|---|---|
| `okit/llm/client.py` | `LLMClient.generate()` / `.structured(schema)`: disk cache, RPM/TPM limiter, full-jitter retries, usage ledger, schema-repair loop |
| `okit/llm/providers.py` | OpenAI + Anthropic adapters over one neutral message/tool format (text, images, tool calls) |
| `okit/llm/cache.py` | content-addressed cache keyed on `sha256(model, prompt_version, schema_version, payload)`, atomic writes |
| `okit/llm/ledger.py` | `usage.jsonl`: tokens, latency, cache hits, cost from a prices file (never hardcoded) |
| `okit/llm/ratelimit.py` | async token-bucket limiter for requests/min and tokens/min |
| `okit/runner/checkpoint.py` | per-row checkpoint/resume with bounded concurrency; failures are retried on resume |
| `okit/perception/image.py` | EXIF-orient, alpha-flatten, downscale, JPEG re-encode under size limits, content hash |
| `okit/perception/audio.py` | OpenAI transcription, cached by audio hash |
| `okit/safety/injection.py` | multilingual (en/fr/es/id/hi/Hinglish/de) injection + scam-lure heuristic → **flag only**; `wrap_untrusted()` fence. On the Sep '26 messages (n=215) it flags exactly the 2 advance-fee scams and none of the 213 others |
| `okit/agent/loop.py` | bounded single-agent tool loop: step/tool-call/token/USD caps, validator feedback, deterministic fallback, per-row JSON trace |
| `okit/evaluation/` | per-field accuracy, macro-F1, confusion, MAE, set-Jaccard; run-vs-run diff (fixed / broke) |
| `okit/report/usage_report.py` | `usage.jsonl` → `usage_report.md` (per model, per purpose, per row) |
| `okit/submit/validate_output.py` | header order, ids complete/unique, enums, ranges, blank fields, generic-text warnings |
| `okit/submit/make_zip.py` | builds `code.zip` without data/venv/caches/.env; refuses if it finds API keys |
| `templates/` | `DECISIONS.md`, `CONSTANTS.md`, `experiments.md`, `interview_brief.md` |

## Setup (PowerShell)

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[openai,anthropic,dev]"
$env:OPENAI_API_KEY = "<key>"      # or put it in a gitignored .env
$env:ANTHROPIC_API_KEY = "<key>"
pytest
```

## Usage sketch

```python
from pydantic import BaseModel
from okit.llm.cache import DiskCache
from okit.llm.client import LLMClient
from okit.llm.ledger import Ledger, load_prices
from okit.llm.providers import make_provider
from okit.llm.ratelimit import RateLimiter
from okit.types import Message

class Observation(BaseModel):
    object_visible: bool
    text_in_image: str

client = LLMClient(
    make_provider("openai"),
    ledger=Ledger("runs/usage.jsonl", load_prices("prices.json")),
    cache=DiskCache(".cache/llm"),
    limiter=RateLimiter(rpm=450, tpm=180_000),
)
obs = await client.structured(Observation, model="gpt-4.1", messages=[Message.user("describe", img.part)],
                              prompt_version="perceive-v1", row_id="r42")
```

CLIs:

```powershell
python -m okit.evaluation score --pred out.csv --gold sample.csv --id id --cat action --num confidence:0.05,amount:0.01:0.005 --set evidence_ids --out evaluation/score.md
python -m okit.evaluation diff --a runs/a.csv --b runs/b.csv --gold sample.csv --id id --cat action
python -m okit.report.usage_report --ledger runs/usage.jsonl --rows 250 --out usage_report.md
python -m okit.submit.validate_output --spec output_spec.json --output output.csv --input test.csv
python -m okit.submit.make_zip --src code --out code.zip --dry-run
```

## Design notes
- **Structured output = one forced tool call**, validated by Pydantic; validation errors go back
  to the model as a tool error for up to N repairs. Same path on both vendors, no strict-schema quirks.
- **Retries live in the client, not the SDK** (`max_retries=0` on SDKs) so every attempt, including
  failures, lands in the ledger and the usage report is exact.
- **The agent loop always has an exit**: when it stops without a valid submission, `fallback()`
  (your deterministic pipeline) produces the row, and `AgentResult.source` records which path won.
- **Injection detection never acts.** It returns a flag; deterministic code decides what the flag means.

## Disclosure
Written before the event as reusable personal tooling. Event-time domain logic goes in the event
repo; disclose this kit in its README and in the interview (see `templates/DECISIONS.md`).
