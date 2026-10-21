"""Speech-to-text via the OpenAI transcription endpoint, cached by audio content hash.

Anthropic has no ASR endpoint, so audio always goes through OpenAI here.
"""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

from pydantic import BaseModel

from okit.llm.cache import DiskCache, cache_key
from okit.llm.ledger import Ledger
from okit.types import Usage


class Transcript(BaseModel):
    path: str
    sha256: str
    model: str
    text: str
    language: str | None = None


async def transcribe(
    path: str | Path,
    *,
    ledger: Ledger,
    cache: DiskCache | None = None,
    model: str = "gpt-4o-transcribe",
    prompt: str | None = None,
    row_id: str | None = None,
    timeout_s: float = 300.0,
) -> Transcript:
    """`prompt` biases vocabulary (names, product terms) and is part of the cache key."""
    import openai

    p = Path(path)
    raw = p.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    key = cache_key(
        model=model, prompt_version=prompt or "", schema_version="asr-v1", payload=digest
    )
    if cache is not None and (hit := cache.get(key)) is not None:
        await ledger.record(
            provider="openai",
            model=model,
            purpose="asr",
            row_id=row_id,
            usage=Usage(),
            latency_ms=0.0,
            cache_hit=True,
            ok=True,
        )
        return Transcript.model_validate(hit)

    client = openai.AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    started = time.perf_counter()
    try:
        resp = await client.audio.transcriptions.create(
            model=model,
            file=(p.name, raw),
            prompt=prompt or openai.omit,
            timeout=timeout_s,
        )
    except openai.APIError as exc:
        await ledger.record(
            provider="openai",
            model=model,
            purpose="asr",
            row_id=row_id,
            usage=Usage(),
            latency_ms=(time.perf_counter() - started) * 1e3,
            cache_hit=False,
            ok=False,
            error=str(exc)[:500],
        )
        raise
    usage = Usage()
    u = getattr(resp, "usage", None)
    if u is not None and getattr(u, "input_tokens", None) is not None:
        usage = Usage(
            input_tokens=u.input_tokens, output_tokens=getattr(u, "output_tokens", 0) or 0
        )
    await ledger.record(
        provider="openai",
        model=model,
        purpose="asr",
        row_id=row_id,
        usage=usage,
        latency_ms=(time.perf_counter() - started) * 1e3,
        cache_hit=False,
        ok=True,
    )
    out = Transcript(
        path=str(p),
        sha256=digest,
        model=model,
        text=resp.text,
        language=getattr(resp, "language", None),
    )
    if cache is not None:
        cache.set(key, out.model_dump())
    return out
