"""Async RPM + TPM limiter (token bucket, continuous refill)."""

from __future__ import annotations

import asyncio
import time


class _Bucket:
    def __init__(self, per_minute: float) -> None:
        self.capacity = per_minute
        self.tokens = per_minute
        self.rate = per_minute / 60.0
        self.updated = time.monotonic()

    def refill(self, now: float) -> None:
        self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
        self.updated = now

    def wait_time(self, amount: float) -> float:
        # A request larger than capacity would never fit; let it through when the bucket is full.
        need = min(amount, self.capacity)
        return 0.0 if self.tokens >= need else (need - self.tokens) / self.rate


class RateLimiter:
    """acquire(estimated_tokens) blocks until both buckets allow the request.

    TPM is charged up front with an estimate; call settle() with the true count
    afterwards so the bucket tracks reality.
    """

    def __init__(self, rpm: float | None = None, tpm: float | None = None) -> None:
        self._rpm = _Bucket(rpm) if rpm else None
        self._tpm = _Bucket(tpm) if tpm else None
        self._lock = asyncio.Lock()

    async def acquire(self, estimated_tokens: int = 0) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                waits = [0.0]
                if self._rpm:
                    self._rpm.refill(now)
                    waits.append(self._rpm.wait_time(1))
                if self._tpm:
                    self._tpm.refill(now)
                    waits.append(self._tpm.wait_time(estimated_tokens))
                delay = max(waits)
                if delay <= 0:
                    if self._rpm:
                        self._rpm.tokens -= 1
                    if self._tpm:
                        self._tpm.tokens -= estimated_tokens
                    return
                await asyncio.sleep(delay)

    def settle(self, estimated_tokens: int, actual_tokens: int) -> None:
        if self._tpm:
            self._tpm.tokens -= actual_tokens - estimated_tokens
