"""Core types for FacadeDriver.

These are the dataclasses and enums that flow through the public API.
Backend implementations, telemetry sinks, and the resilience layer all
operate on these types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal


# Type aliases
Message = dict[str, Any]
"""Chat message. Must have 'role' (str) and 'content' (str).
Example: {'role': 'user', 'content': 'Hello'}"""


class CircuitState(str, Enum):
    """Circuit breaker state machine."""

    CLOSED = "closed"      # requests flow normally
    OPEN = "open"          # requests are blocked, fallback is used
    HALF_OPEN = "half_open"  # one trial request allowed through


@dataclass
class HealthStatus:
    """Health of a model or route."""

    model: str
    circuit_state: CircuitState
    error_rate: float
    request_count: int
    error_count: int
    last_error: str | None = None
    last_success_ts: float | None = None

    @property
    def healthy(self) -> bool:
        return self.circuit_state in (CircuitState.CLOSED, CircuitState.HALF_OPEN)


@dataclass
class BackendResponse:
    """Raw response from a backend (provider SDK call).

    Backends return this. The resilience layer wraps it into a Response
    with telemetry.
    """

    content: str
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    raw: Any = None
    cost_usd: float | None = None
    latency_ms: float | None = None


@dataclass
class Response:
    """Public response from FacadeDriver.generate().

    Carries the content plus the telemetry that application code or
    observability tooling might need.
    """

    content: str
    model: str
    provider: str
    route: str
    cost_usd: float | None
    latency_ms: float
    input_tokens: int
    output_tokens: int
    fallback_used: bool
    fallback_chain: list[str]
    circuit_breaker_trip: bool
    request_id: str
    raw: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.content


class FacadeDriverError(Exception):
    """Base class for FacadeDriver errors."""


class AllProvidersFailedError(FacadeDriverError):
    """All models in the fallback chain failed."""

    def __init__(self, route: str, chain: list[str], errors: list[str]):
        self.route = route
        self.chain = chain
        self.errors = errors
        super().__init__(
            f"All providers failed for route '{route}'. "
            f"Chain tried: {chain}. Errors: {errors}"
        )


class RouteNotFoundError(FacadeDriverError):
    """The requested route is not in the config."""

    def __init__(self, route: str):
        self.route = route
        super().__init__(f"Route '{route}' not found in config")


class CircuitOpenError(FacadeDriverError):
    """Circuit breaker is open for a model."""

    def __init__(self, model: str, state: CircuitState):
        self.model = model
        self.state = state
        super().__init__(f"Circuit breaker {state.value} for model '{model}'")


class BackendError(FacadeDriverError):
    """A backend call failed."""

    def __init__(self, model: str, provider: str, original: Exception):
        self.model = model
        self.provider = provider
        self.original = original
        super().__init__(f"Backend error for model '{model}' ({provider}): {original}")
