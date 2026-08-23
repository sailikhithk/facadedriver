"""Unit tests for FacadeDriver core: routing, fallback, retry, circuit breaker, telemetry."""

from __future__ import annotations

import asyncio
import json

import pytest

from facadedriver import (
    Config,
    FacadeDriver,
    MockBackend,
    AsyncMockBackend,
)
from facadedriver.resilience import CircuitBreaker, CircuitState
from facadedriver.telemetry import NullSink, StructlogSink, TelemetryEvent, FileSink
from facadedriver.types import AllProvidersFailedError, RouteNotFoundError


# --- Config ------------------------------------------------------------------


def test_config_from_dict_minimal():
    cfg = Config.from_dict({})
    assert cfg.routes == {}
    assert cfg.backend.type == "raw_sdk"


def test_config_from_dict_with_routes():
    cfg = Config.from_dict({
        "routes": {
            "r": {
                "primary": "gpt-4o-mini",
                "fallback": ["claude-3-5-sonnet"],
                "retry": {"count": 3, "backoff": "linear"},
            }
        }
    })
    r = cfg.routes["r"]
    assert r.primary == "gpt-4o-mini"
    assert r.fallback == ["claude-3-5-sonnet"]
    assert r.retry.count == 3
    assert r.retry.backoff == "linear"


def test_config_env_expansion(monkeypatch):
    monkeypatch.setenv("TEST_KEY", "secret123")
    cfg = Config.from_dict({"providers": {"openai": {"api_key": "${TEST_KEY}"}}})
    assert cfg.providers["openai"].api_key == "secret123"


def test_config_route_not_found():
    cfg = Config.from_dict({})
    with pytest.raises(RouteNotFoundError):
        cfg.route("nope")


# --- Routing -----------------------------------------------------------------


def test_router_chain():
    from facadedriver.routing import Router
    from facadedriver.config import RouteConfig

    r = Router({
        "r": RouteConfig(primary="a", fallback=["b", "c"]),
    })
    assert r.chain("r") == ["a", "b", "c"]


def test_router_swap():
    from facadedriver.routing import Router
    from facadedriver.config import RouteConfig

    r = Router({"r": RouteConfig(primary="a", fallback=["b"])})
    r.swap("r", "x")
    assert r.chain("r") == ["x", "b"]


def test_router_swap_missing_route():
    from facadedriver.routing import Router

    r = Router({})
    with pytest.raises(RouteNotFoundError):
        r.swap("nope", "x")


# --- Circuit breaker ---------------------------------------------------------


def test_circuit_breaker_stays_closed_under_thresholds():
    cb = CircuitBreaker(error_rate_threshold=0.5, min_requests=4)
    for _ in range(3):
        cb.record_failure("m")
    assert cb.state("m") == CircuitState.CLOSED


def test_circuit_breaker_opens_at_threshold():
    cb = CircuitBreaker(error_rate_threshold=0.5, min_requests=4)
    for _ in range(4):
        cb.record_failure("m")
    assert cb.state("m") == CircuitState.OPEN
    assert cb.allow("m") is False


def test_circuit_breaker_half_open_after_cooldown():
    cb = CircuitBreaker(error_rate_threshold=0.5, min_requests=2, cooldown_s=0.0)
    cb.record_failure("m")
    cb.record_failure("m")
    assert cb.state("m") == CircuitState.OPEN
    # cooldown_s=0 means immediately half-open
    assert cb.allow("m") is True
    assert cb.state("m") == CircuitState.HALF_OPEN


def test_circuit_breaker_closes_on_success():
    cb = CircuitBreaker(error_rate_threshold=0.5, min_requests=2, cooldown_s=0.0)
    cb.record_failure("m")
    cb.record_failure("m")
    cb.allow("m")  # -> half_open
    cb.record_success("m")
    assert cb.state("m") == CircuitState.CLOSED


# --- Driver: generate --------------------------------------------------------


def _make_driver(fail: set[str] | None = None, **kw):
    cfg = Config.from_dict({
        "routes": {
            "summarize": {
                "primary": "gpt-4o-mini",
                "fallback": ["claude-3-5-sonnet", "gemini-1.5-flash"],
                "retry": {"count": 0, "backoff": "fixed", "base_ms": 1},
            }
        }
    })
    return FacadeDriver(
        cfg,
        backend=MockBackend(fail_models=fail or set()),
        telemetry_sink=NullSink(),
        **kw,
    )


def test_generate_primary_success():
    d = _make_driver()
    r = d.generate("summarize", [{"role": "user", "content": "hi"}])
    assert r.model == "gpt-4o-mini"
    assert r.fallback_used is False
    assert r.fallback_chain == ["gpt-4o-mini"]
    assert r.content.startswith("[mock:")
    assert r.request_id


def test_generate_fallback_on_primary_failure():
    d = _make_driver(fail={"gpt-4o-mini"})
    r = d.generate("summarize", [{"role": "user", "content": "hi"}])
    assert r.model == "claude-3-5-sonnet"
    assert r.fallback_used is True
    assert r.fallback_chain == ["gpt-4o-mini", "claude-3-5-sonnet"]


def test_generate_all_fail_raises():
    d = _make_driver(fail={"gpt-4o-mini", "claude-3-5-sonnet", "gemini-1.5-flash"})
    with pytest.raises(AllProvidersFailedError) as exc:
        d.generate("summarize", [{"role": "user", "content": "hi"}])
    assert exc.value.route == "summarize"
    assert len(exc.value.chain) == 3


def test_generate_route_not_found():
    d = _make_driver()
    with pytest.raises(RouteNotFoundError):
        d.generate("nope", [{"role": "user", "content": "hi"}])


def test_generate_retry_then_success():
    cfg = Config.from_dict({
        "routes": {
            "r": {
                "primary": "m1",
                "fallback": [],
                "retry": {"count": 2, "backoff": "fixed", "base_ms": 1},
            }
        }
    })

    # A backend that fails twice then succeeds
    class FlakyBackend:
        def __init__(self):
            self.calls = 0

        def generate(self, model, messages, **kw):
            self.calls += 1
            if self.calls < 3:
                raise RuntimeError("flake")
            from facadedriver.types import BackendResponse
            return BackendResponse(
                content="ok", model=model, provider="test",
                input_tokens=1, output_tokens=1, cost_usd=0.0, latency_ms=1.0,
            )

    d = FacadeDriver(cfg, backend=FlakyBackend(), telemetry_sink=NullSink())
    r = d.generate("r", [{"role": "user", "content": "hi"}])
    assert r.content == "ok"
    assert r.model == "m1"


def test_swap_changes_primary():
    d = _make_driver()
    d.swap("summarize", "claude-3-5-sonnet")
    r = d.generate("summarize", [{"role": "user", "content": "hi"}])
    assert r.model == "claude-3-5-sonnet"


def test_health_reports_stats():
    d = _make_driver(fail={"gpt-4o-mini"})
    try:
        d.generate("summarize", [{"role": "user", "content": "hi"}])
    except Exception:
        pass
    h = d.health("gpt-4o-mini")
    assert h.model == "gpt-4o-mini"
    assert h.request_count >= 1
    assert h.error_count >= 1


# --- Telemetry ---------------------------------------------------------------


def test_structlog_sink_emits_json(capsys):
    sink = StructlogSink()
    sink.emit(TelemetryEvent(
        request_id="r1", route="summarize", model="gpt-4o-mini",
        provider="mock", cost_usd=0.001, latency_ms=12.3,
        input_tokens=5, output_tokens=7, fallback_used=False,
        fallback_chain=["gpt-4o-mini"], circuit_breaker_trip=False,
    ))
    out = capsys.readouterr().out.strip()
    payload = json.loads(out)
    assert payload["request_id"] == "r1"
    assert payload["model"] == "gpt-4o-mini"
    assert payload["cost_usd"] == 0.001


def test_null_sink_noop():
    NullSink().emit(TelemetryEvent(
        request_id="r", route="", model="", provider="",
        cost_usd=None, latency_ms=0, input_tokens=0, output_tokens=0,
        fallback_used=False, fallback_chain=[], circuit_breaker_trip=False,
    ))  # should not raise


def test_file_sink(tmp_path):
    p = tmp_path / "events.jsonl"
    sink = FileSink(str(p))
    sink.emit(TelemetryEvent(
        request_id="r1", route="x", model="m", provider="p",
        cost_usd=0.0, latency_ms=1.0, input_tokens=1, output_tokens=1,
        fallback_used=False, fallback_chain=["m"], circuit_breaker_trip=False,
    ))
    lines = p.read_text().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["request_id"] == "r1"


# --- Async ---------------------------------------------------------------


def test_async_generate():
    cfg = Config.from_dict({
        "routes": {"r": {"primary": "gpt-4o-mini", "fallback": ["claude-3-5-sonnet"]}}
    })
    d = FacadeDriver(
        cfg, backend=AsyncMockBackend(latency_ms=1), telemetry_sink=NullSink(),
    )
    r = asyncio.run(
        d.agenerate("r", [{"role": "user", "content": "hi"}])
    )
    assert r.model == "gpt-4o-mini"
    assert r.content.startswith("[async-mock:")


def test_async_fallback():
    cfg = Config.from_dict({
        "routes": {"r": {
            "primary": "gpt-4o-mini", "fallback": ["claude-3-5-sonnet"],
            "retry": {"count": 0, "backoff": "fixed", "base_ms": 1},
        }}
    })
    d = FacadeDriver(
        cfg,
        backend=AsyncMockBackend(latency_ms=1, fail_models={"gpt-4o-mini"}),
        telemetry_sink=NullSink(),
    )
    r = asyncio.run(
        d.agenerate("r", [{"role": "user", "content": "hi"}])
    )
    assert r.model == "claude-3-5-sonnet"
    assert r.fallback_used is True
