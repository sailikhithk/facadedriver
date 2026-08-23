"""FacadeDriver - the main entry point.

Orchestrates routing, backends, retry, fallback chains, circuit
breaking, and telemetry for multi-LLM production systems.

Typical usage:

    from facadedriver import FacadeDriver, Config, MockBackend

    cfg = Config.from_yaml("facadedriver.yaml")
    driver = FacadeDriver(cfg, backend=MockBackend())
    resp = driver.generate("summarize", [{"role": "user", "content": "hi"}])
    print(resp.content)
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

from facadedriver.backends import Backend
from facadedriver.config import Config, RetryConfig
from facadedriver.resilience import CircuitBreaker
from facadedriver.routing import Router
from facadedriver.telemetry import (
    NullSink,
    StructlogSink,
    TelemetryEvent,
    TelemetrySink,
)
from facadedriver.types import (
    AllProvidersFailedError,
    BackendError,
    BackendResponse,
    CircuitOpenError,
    HealthStatus,
    Message,
    Response,
)


def _backoff_ms(attempt: int, cfg: RetryConfig) -> float:
    if cfg.backoff == "fixed":
        return float(cfg.base_ms)
    if cfg.backoff == "linear":
        return float(cfg.base_ms * (attempt + 1))
    # exponential
    return float(min(cfg.base_ms * (2**attempt), cfg.max_ms))


class FacadeDriver:
    """Model-agnostic orchestration layer.

    Args:
        config: typed Config (routes, providers, telemetry, etc.)
        backend: Backend implementation (RawSDKBackend, LiteLLMBackend, MockBackend, or custom)
        telemetry_sink: optional sink; defaults to StructlogSink if config.telemetry.sinks
            includes "structlog", else NullSink.
        circuit_breaker: optional custom CircuitBreaker; a default one is created per-route.
    """

    def __init__(
        self,
        config: Config,
        backend: Backend,
        *,
        telemetry_sink: TelemetrySink | None = None,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        self.config = config
        self.backend = backend
        self.router = Router(config.routes)
        self.breaker = circuit_breaker or CircuitBreaker(
            error_rate_threshold=0.15,
            min_requests=20,
            cooldown_s=60.0,
        )
        if telemetry_sink is not None:
            self.sink = telemetry_sink
        elif "structlog" in config.telemetry.sinks:
            self.sink = StructlogSink()
        elif "file" in config.telemetry.sinks and config.telemetry.file_path:
            from facadedriver.telemetry import FileSink

            self.sink = FileSink(config.telemetry.file_path)
        else:
            self.sink = NullSink()

    def generate(
        self,
        route: str,
        messages: list[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> Response:
        """Generate a completion for the given route.

        Walks the route's model chain (primary + fallbacks). For each
        model: checks the circuit breaker, retries per the route's retry
        config, and falls back to the next model on failure. Emits a
        TelemetryEvent at the end.
        """
        chain = self.router.chain(route)
        route_cfg = self.router.config(route)
        request_id = uuid.uuid4().hex[:16]
        start = time.perf_counter()
        errors: list[str] = []
        fallback_chain_tried: list[str] = []
        circuit_trip = False

        for idx, model in enumerate(chain):
            fallback_chain_tried.append(model)
            if not self.breaker.allow(model):
                circuit_trip = True
                errors.append(f"circuit open for {model}")
                continue

            resp = self._try_model(
                model,
                messages,
                route_cfg.retry,
                temperature,
                max_tokens,
                kwargs,
            )
            if resp is not None:
                latency_ms = (time.perf_counter() - start) * 1000
                response = Response(
                    content=resp.content,
                    model=resp.model,
                    provider=resp.provider,
                    route=route,
                    cost_usd=resp.cost_usd,
                    latency_ms=latency_ms,
                    input_tokens=resp.input_tokens,
                    output_tokens=resp.output_tokens,
                    fallback_used=idx > 0,
                    fallback_chain=fallback_chain_tried,
                    circuit_breaker_trip=circuit_trip,
                    request_id=request_id,
                    raw=resp.raw,
                )
                self._emit(response, route_cfg, extra={})
                return response

            # _try_model already recorded failures with the breaker

        latency_ms = (time.perf_counter() - start) * 1000
        self._emit(
            Response(
                content="",
                model="",
                provider="",
                route=route,
                cost_usd=None,
                latency_ms=latency_ms,
                input_tokens=0,
                output_tokens=0,
                fallback_used=len(fallback_chain_tried) > 1,
                fallback_chain=fallback_chain_tried,
                circuit_breaker_trip=circuit_trip,
                request_id=request_id,
            ),
            route_cfg,
            extra={"errors": errors, "failed": True},
        )
        raise AllProvidersFailedError(route, fallback_chain_tried, errors)

    def _try_model(
        self,
        model: str,
        messages: list[Message],
        retry: RetryConfig,
        temperature: float,
        max_tokens: int | None,
        kwargs: dict[str, Any],
    ) -> BackendResponse | None:
        last_err: Exception | None = None
        for attempt in range(retry.count + 1):
            try:
                resp = self.backend.generate(
                    model,
                    messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **kwargs,
                )
                self.breaker.record_success(model)
                return resp
            except Exception as e:  # noqa: BLE001
                last_err = e
                self.breaker.record_failure(model, str(e))
                if attempt < retry.count:
                    time.sleep(_backoff_ms(attempt, retry) / 1000.0)
        return None

    def _emit(self, resp: Response, route_cfg: Any, *, extra: dict[str, Any]) -> None:
        tc = self.config.telemetry
        event = TelemetryEvent(
            request_id=resp.request_id,
            route=resp.route,
            model=resp.model,
            provider=resp.provider,
            cost_usd=resp.cost_usd if tc.log_cost else None,
            latency_ms=resp.latency_ms if tc.log_latency else 0.0,
            input_tokens=resp.input_tokens if tc.log_tokens else 0,
            output_tokens=resp.output_tokens if tc.log_tokens else 0,
            fallback_used=resp.fallback_used if tc.log_fallback else False,
            fallback_chain=resp.fallback_chain if tc.log_fallback else [],
            circuit_breaker_trip=resp.circuit_breaker_trip,
            extra=extra,
        )
        try:
            self.sink.emit(event)
        except Exception:  # noqa: BLE001
            # Telemetry must never break the request.
            pass

    def swap(self, route: str, model: str) -> None:
        """Runtime swap of a route's primary model."""
        self.router.swap(route, model)

    def health(self, model: str) -> HealthStatus:
        from facadedriver.types import CircuitState

        return HealthStatus(
            model=model,
            circuit_state=self.breaker.state(model),
            error_rate=self.breaker.error_rate(model),
            request_count=self.breaker._get(model).requests,
            error_count=self.breaker._get(model).errors,
            last_error=self.breaker._get(model).last_error,
            last_success_ts=self.breaker._get(model).last_success_ts,
        )

    def routes(self) -> list[str]:
        return self.router.routes()

    # ------------------------------------------------------------------
    # Async support
    # ------------------------------------------------------------------

    async def agenerate(
        self,
        route: str,
        messages: list[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> Response:
        """Async version of generate().

        Requires an async backend (AsyncBackend). If the configured
        backend is sync-only, this raises TypeError.
        """
        from facadedriver.async_support import AsyncBackend

        if not isinstance(self.backend, AsyncBackend):
            raise TypeError(
                f"Backend {type(self.backend).__name__} does not implement AsyncBackend. "
                "Use AsyncMockBackend, AsyncRawSDKBackend, or any class with an async generate()."
            )

        chain = self.router.chain(route)
        route_cfg = self.router.config(route)
        request_id = uuid.uuid4().hex[:16]
        start = time.perf_counter()
        errors: list[str] = []
        fallback_chain_tried: list[str] = []
        circuit_trip = False

        for idx, model in enumerate(chain):
            fallback_chain_tried.append(model)
            if not self.breaker.allow(model):
                circuit_trip = True
                errors.append(f"circuit open for {model}")
                continue

            resp = await self._atry_model(
                model, messages, route_cfg.retry, temperature, max_tokens, kwargs,
            )
            if resp is not None:
                latency_ms = (time.perf_counter() - start) * 1000
                response = Response(
                    content=resp.content, model=resp.model, provider=resp.provider,
                    route=route, cost_usd=resp.cost_usd, latency_ms=latency_ms,
                    input_tokens=resp.input_tokens, output_tokens=resp.output_tokens,
                    fallback_used=idx > 0, fallback_chain=fallback_chain_tried,
                    circuit_breaker_trip=circuit_trip, request_id=request_id,
                    raw=resp.raw,
                )
                self._emit(response, route_cfg, extra={})
                return response

        latency_ms = (time.perf_counter() - start) * 1000
        self._emit(
            Response(
                content="", model="", provider="", route=route, cost_usd=None,
                latency_ms=latency_ms, input_tokens=0, output_tokens=0,
                fallback_used=len(fallback_chain_tried) > 1,
                fallback_chain=fallback_chain_tried,
                circuit_breaker_trip=circuit_trip, request_id=request_id,
            ),
            route_cfg, extra={"errors": errors, "failed": True},
        )
        raise AllProvidersFailedError(route, fallback_chain_tried, errors)

    async def _atry_model(
        self, model, messages, retry, temperature, max_tokens, kwargs,
    ) -> BackendResponse | None:
        for attempt in range(retry.count + 1):
            try:
                resp = await self.backend.generate(  # type: ignore[attr-defined]
                    model, messages, temperature=temperature,
                    max_tokens=max_tokens, **kwargs,
                )
                self.breaker.record_success(model)
                return resp
            except Exception as e:  # noqa: BLE001
                self.breaker.record_failure(model, str(e))
                if attempt < retry.count:
                    await asyncio.sleep(_backoff_ms(attempt, retry) / 1000.0)
        return None
