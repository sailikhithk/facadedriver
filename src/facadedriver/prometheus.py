"""Prometheus metrics exporter for FacadeDriver.

Exposes counters and histograms for:
    facadedriver_requests_total{route,model,provider,status}
    facadedriver_cost_usd_total{route,model,provider}
    facadedriver_latency_ms_bucket{route,model,provider}
    facadedriver_tokens_total{route,model,provider,direction}
    facadedriver_fallback_total{route}
    facadedriver_circuit_open_total{model}

Usage:
    from facadedriver.prometheus import PrometheusSink, run_metrics_server
    driver = FacadeDriver(cfg, backend=..., telemetry_sink=PrometheusSink())
    run_metrics_server(port=9090)  # serves /metrics
"""

from __future__ import annotations

from typing import Any

from facadedriver.telemetry import TelemetryEvent, TelemetrySink


class PrometheusSink:
    """Telemetry sink that updates in-process Prometheus metrics.

    Requires the `prometheus_client` package. If not installed, the
    sink degrades to a no-op and prints a warning once.
    """

    def __init__(self) -> None:
        try:
            from prometheus_client import Counter, Histogram, start_http_server  # type: ignore
            self._available = True
            self._Counter = Counter
            self._Histogram = Histogram
            self._start_http_server = start_http_server
        except ImportError:
            self._available = False
            return
        self._requests = self._Counter(
            "facadedriver_requests_total",
            "Total generate() calls",
            ["route", "model", "provider", "status"],
        )
        self._cost = self._Counter(
            "facadedriver_cost_usd_total",
            "Total USD spent",
            ["route", "model", "provider"],
        )
        self._latency = self._Histogram(
            "facadedriver_latency_ms",
            "Generate latency in ms",
            ["route", "model", "provider"],
            buckets=(1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000),
        )
        self._tokens = self._Counter(
            "facadedriver_tokens_total",
            "Total tokens",
            ["route", "model", "provider", "direction"],
        )
        self._fallback = self._Counter(
            "facadedriver_fallback_total",
            "Total calls that used a fallback model",
            ["route"],
        )
        self._circuit_open = self._Counter(
            "facadedriver_circuit_open_total",
            "Total calls blocked by an open circuit",
            ["model"],
        )

    def emit(self, event: TelemetryEvent) -> None:
        if not self._available:
            return
        status = "failed" if event.extra.get("failed") else "ok"
        self._requests.labels(
            route=event.route, model=event.model or "none",
            provider=event.provider or "none", status=status,
        ).inc()
        if event.cost_usd is not None:
            self._cost.labels(
                route=event.route, model=event.model or "none",
                provider=event.provider or "none",
            ).inc(event.cost_usd)
        if event.latency_ms:
            self._latency.labels(
                route=event.route, model=event.model or "none",
                provider=event.provider or "none",
            ).observe(event.latency_ms)
        if event.input_tokens:
            self._tokens.labels(
                route=event.route, model=event.model or "none",
                provider=event.provider or "none", direction="input",
            ).inc(event.input_tokens)
        if event.output_tokens:
            self._tokens.labels(
                route=event.route, model=event.model or "none",
                provider=event.provider or "none", direction="output",
            ).inc(event.output_tokens)
        if event.fallback_used:
            self._fallback.labels(route=event.route).inc()
        if event.circuit_breaker_trip:
            self._circuit_open.labels(model=event.model or "none").inc()


def run_metrics_server(port: int = 9090, addr: str = "0.0.0.0") -> None:
    """Start a background HTTP server that serves /metrics."""
    try:
        from prometheus_client import start_http_server  # type: ignore
    except ImportError as e:
        raise ImportError(
            "prometheus_client not installed. Run `pip install prometheus_client`."
        ) from e
    start_http_server(port, addr=addr)
