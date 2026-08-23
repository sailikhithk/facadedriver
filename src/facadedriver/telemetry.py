"""Telemetry sinks for structured logging of cost, latency, and fallbacks.

A TelemetrySink receives a TelemetryEvent for every generate() call.
The default StructlogSink logs JSON lines to stdout. FileSink writes
to a file. Custom sinks (Prometheus, Datadog, etc.) can be plugged in
via the TelemetrySink protocol.
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Protocol, TextIO, runtime_checkable


@dataclass
class TelemetryEvent:
    """One event per generate() call."""

    request_id: str
    route: str
    model: str
    provider: str
    cost_usd: float | None
    latency_ms: float
    input_tokens: int
    output_tokens: int
    fallback_used: bool
    fallback_chain: list[str]
    circuit_breaker_trip: bool
    timestamp: float = field(default_factory=time.time)
    extra: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class TelemetrySink(Protocol):
    def emit(self, event: TelemetryEvent) -> None: ...


class StructlogSink:
    """Emit JSON lines to a stream (default stdout)."""

    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = stream or sys.stdout

    def emit(self, event: TelemetryEvent) -> None:
        payload = {
            "ts": event.timestamp,
            "request_id": event.request_id,
            "route": event.route,
            "model": event.model,
            "provider": event.provider,
            "cost_usd": event.cost_usd,
            "latency_ms": round(event.latency_ms, 2),
            "input_tokens": event.input_tokens,
            "output_tokens": event.output_tokens,
            "fallback_used": event.fallback_used,
            "fallback_chain": event.fallback_chain,
            "circuit_breaker_trip": event.circuit_breaker_trip,
            **event.extra,
        }
        self._stream.write(json.dumps(payload, default=str) + "\n")
        self._stream.flush()


class FileSink:
    """Append JSON lines to a file."""

    def __init__(self, path: str) -> None:
        self._path = path

    def emit(self, event: TelemetryEvent) -> None:
        with open(self._path, "a") as f:
            f.write(json.dumps(event.__dict__, default=str) + "\n")


class NullSink:
    """No-op sink for tests."""

    def emit(self, event: TelemetryEvent) -> None:
        pass
