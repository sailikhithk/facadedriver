"""Typed config for FacadeDriver.

Loaded from YAML or constructed from a dict. Validates routes, providers,
backend, and telemetry config.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from facadedriver.types import FacadeDriverError


_ENV_VAR_RE = re.compile(r"\$\{([A-Z0-9_]+)\}")


def _expand_env(value: str) -> str:
    """Expand ${ENV_VAR} references in a string."""

    def _replace(match: re.Match[str]) -> str:
        var = match.group(1)
        return os.environ.get(var, "")

    return _ENV_VAR_RE.sub(_replace, value)


def _expand_env_recursive(obj: Any) -> Any:
    if isinstance(obj, str):
        return _expand_env(obj)
    if isinstance(obj, dict):
        return {k: _expand_env_recursive(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_env_recursive(v) for v in obj]
    return obj


@dataclass
class RetryConfig:
    count: int = 2
    backoff: str = "exponential"  # exponential | linear | fixed
    base_ms: int = 200
    max_ms: int = 10_000


@dataclass
class CircuitBreakerConfig:
    error_rate_threshold: float = 0.15
    min_requests: int = 20
    cooldown_s: float = 60.0
    quality_check: str | None = None


@dataclass
class RouteConfig:
    primary: str
    fallback: list[str] = field(default_factory=list)
    retry: RetryConfig = field(default_factory=RetryConfig)
    circuit_breaker: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    quality_check: str | None = None  # dotted path to a callable


@dataclass
class ProviderConfig:
    api_key: str | None = None
    base_url: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class BackendConfig:
    type: str = "raw_sdk"  # raw_sdk | litellm | custom
    module: str | None = None
    class_name: str | None = None
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class TelemetryConfig:
    sinks: list[str] = field(default_factory=lambda: ["structlog"])
    log_cost: bool = True
    log_latency: bool = True
    log_tokens: bool = True
    log_fallback: bool = True
    prometheus_port: int = 9090
    file_path: str | None = None


@dataclass
class ServerConfig:
    enabled: bool = False
    host: str = "0.0.0.0"
    port: int = 8000


@dataclass
class Config:
    routes: dict[str, RouteConfig] = field(default_factory=dict)
    providers: dict[str, ProviderConfig] = field(default_factory=dict)
    backend: BackendConfig = field(default_factory=BackendConfig)
    telemetry: TelemetryConfig = field(default_factory=TelemetryConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Config:
        data = _expand_env_recursive(data)
        routes = {}
        for name, r in (data.get("routes") or {}).items():
            retry = RetryConfig(**(r.get("retry") or {}))
            cb = CircuitBreakerConfig(**(r.get("circuit_breaker") or {}))
            routes[name] = RouteConfig(
                primary=r["primary"],
                fallback=list(r.get("fallback") or []),
                retry=retry,
                circuit_breaker=cb,
                quality_check=r.get("quality_check"),
            )
        providers = {
            name: ProviderConfig(
                api_key=p.get("api_key"),
                base_url=p.get("base_url"),
                extra={k: v for k, v in p.items() if k not in ("api_key", "base_url")},
            )
            for name, p in (data.get("providers") or {}).items()
        }
        backend_raw = data.get("backend") or {}
        backend = BackendConfig(
            type=backend_raw.get("type", "raw_sdk"),
            module=backend_raw.get("module"),
            class_name=backend_raw.get("class"),
            options=backend_raw.get("options") or {},
        )
        tel_raw = data.get("telemetry") or {}
        telemetry = TelemetryConfig(
            sinks=tel_raw.get("sinks") or ["structlog"],
            log_cost=tel_raw.get("log_cost", True),
            log_latency=tel_raw.get("log_latency", True),
            log_tokens=tel_raw.get("log_tokens", True),
            log_fallback=tel_raw.get("log_fallback", True),
            prometheus_port=tel_raw.get("prometheus_port", 9090),
            file_path=tel_raw.get("file_path"),
        )
        srv_raw = data.get("server") or {}
        server = ServerConfig(
            enabled=srv_raw.get("enabled", False),
            host=srv_raw.get("host", "0.0.0.0"),
            port=srv_raw.get("port", 8000),
        )
        return cls(
            routes=routes,
            providers=providers,
            backend=backend,
            telemetry=telemetry,
            server=server,
            raw=data,
        )

    @classmethod
    def from_yaml(cls, path: str | Path) -> Config:
        p = Path(path)
        if not p.exists():
            raise FacadeDriverError(f"Config file not found: {path}")
        with p.open() as f:
            data = yaml.safe_load(f) or {}
        return cls.from_dict(data)

    def route(self, name: str) -> RouteConfig:
        if name not in self.routes:
            from facadedriver.types import RouteNotFoundError

            raise RouteNotFoundError(name)
        return self.routes[name]
