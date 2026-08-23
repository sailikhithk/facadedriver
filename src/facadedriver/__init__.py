"""FacadeDriver: model-agnostic orchestration for multi-LLM production systems.

Public API:
    FacadeDriver        - main entry point
    Response            - result of a generate() call
    Message             - chat message dict (role, content)
    Backend             - protocol for pluggable backends
    TelemetrySink       - protocol for pluggable telemetry sinks
    CircuitState        - circuit breaker state enum
    Config              - typed config (loaded from YAML)
"""

from facadedriver.config import Config
from facadedriver.driver import FacadeDriver
from facadedriver.backends import Backend, BackendResponse, MockBackend, RawSDKBackend
from facadedriver.backends.litellm import LiteLLMBackend
from facadedriver.async_support import (
    AsyncBackend,
    AsyncMockBackend,
    AsyncRawSDKBackend,
)
from facadedriver.resilience import CircuitBreaker, CircuitState
from facadedriver.routing import Router, RouteConfig
from facadedriver.telemetry import (
    TelemetrySink,
    TelemetryEvent,
    StructlogSink,
    FileSink,
)
from facadedriver.types import Message, Response, HealthStatus

__version__ = "0.1.0"
__all__ = [
    "FacadeDriver",
    "Response",
    "Message",
    "Backend",
    "BackendResponse",
    "MockBackend",
    "RawSDKBackend",
    "LiteLLMBackend",
    "AsyncBackend",
    "AsyncMockBackend",
    "AsyncRawSDKBackend",
    "CircuitBreaker",
    "CircuitState",
    "Router",
    "RouteConfig",
    "TelemetrySink",
    "TelemetryEvent",
    "StructlogSink",
    "FileSink",
    "Config",
    "HealthStatus",
    "__version__",
]
