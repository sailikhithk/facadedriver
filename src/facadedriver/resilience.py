"""Circuit breaker for per-model failure protection.

Tracks success/failure per model. When the error rate exceeds a
threshold over a minimum number of requests, the circuit opens and
blocks calls to that model for a cooldown period. After cooldown, one
trial request is allowed (half-open). If it succeeds, the circuit
closes; if it fails, it reopens.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from facadedriver.types import CircuitState


@dataclass
class _ModelStats:
    requests: int = 0
    errors: int = 0
    last_error: str | None = None
    last_success_ts: float | None = None
    opened_at: float | None = None
    state: CircuitState = CircuitState.CLOSED


class CircuitBreaker:
    """Per-model circuit breaker.

    Args:
        error_rate_threshold: fraction of errors that trips the breaker.
        min_requests: minimum requests before the breaker can trip.
        cooldown_s: seconds the breaker stays open before half-open.
    """

    def __init__(
        self,
        *,
        error_rate_threshold: float = 0.15,
        min_requests: int = 20,
        cooldown_s: float = 60.0,
    ) -> None:
        self.error_rate_threshold = error_rate_threshold
        self.min_requests = min_requests
        self.cooldown_s = cooldown_s
        self._stats: dict[str, _ModelStats] = {}

    def _get(self, model: str) -> _ModelStats:
        return self._stats.setdefault(model, _ModelStats())

    def allow(self, model: str) -> bool:
        """Return True if a call to `model` is allowed right now."""
        s = self._get(model)
        if s.state == CircuitState.CLOSED:
            return True
        if s.state == CircuitState.OPEN:
            if s.opened_at and (time.time() - s.opened_at) >= self.cooldown_s:
                s.state = CircuitState.HALF_OPEN
                return True
            return False
        # HALF_OPEN: only one trial in flight. We allow it; the next
        # record_success/record_failure will resolve the state.
        return True

    def record_success(self, model: str) -> None:
        s = self._get(model)
        s.requests += 1
        s.last_success_ts = time.time()
        if s.state in (CircuitState.HALF_OPEN, CircuitState.OPEN):
            s.state = CircuitState.CLOSED
            s.opened_at = None

    def record_failure(self, model: str, error: str = "") -> None:
        s = self._get(model)
        s.requests += 1
        s.errors += 1
        s.last_error = error
        if s.state == CircuitState.HALF_OPEN:
            s.state = CircuitState.OPEN
            s.opened_at = time.time()
        elif s.requests >= self.min_requests:
            rate = s.errors / s.requests
            if rate >= self.error_rate_threshold:
                s.state = CircuitState.OPEN
                s.opened_at = time.time()

    def state(self, model: str) -> CircuitState:
        return self._get(model).state

    def error_rate(self, model: str) -> float:
        s = self._get(model)
        return s.errors / s.requests if s.requests else 0.0

    def reset(self, model: str | None = None) -> None:
        if model is None:
            self._stats.clear()
        else:
            self._stats.pop(model, None)
