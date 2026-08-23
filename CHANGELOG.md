# Changelog

All notable changes to FacadeDriver are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/).

## [0.1.0] - 2026-08-22

### Added
- Core `FacadeDriver` class with provider-agnostic `generate()` API.
- `Router` with per-route model chains and runtime swap.
- `CircuitBreaker` with per-model state machine (closed/open/half-open).
- `RawSDKBackend` supporting OpenAI, Anthropic, and Google GenAI SDKs.
- `LiteLLMBackend` as a pluggable alternative (uses litellm.completion).
- `MockBackend` and `AsyncMockBackend` for tests and demos.
- Async support: `agenerate()` with `AsyncBackend` protocol.
- Retry with exponential/linear/fixed backoff.
- Fallback chains with graceful degradation.
- `AllProvidersFailedError` with chain and error details.
- `TelemetrySink` protocol with `StructlogSink`, `FileSink`, `NullSink`.
- `PrometheusSink` with counters and histograms.
- CLI (`facadedriver` command): generate, routes, swap, health, replay, serve.
- FastAPI server mode: POST /generate, GET /routes, GET /health, POST /swap.
- Plugin system with entry-point discovery and dotted-path class loading.
- Typed `Config` loaded from YAML or dict with `${ENV_VAR}` expansion.
- 23 unit tests covering config, routing, breaker, fallback, retry, telemetry, async.
- Benchmark suite measuring overhead and throughput.
- Four example scripts: quickstart, live-swap, failure-modes, talk demo.
- MkDocs documentation site.
- Sample `facadedriver.yaml` configuration.
- MIT license.
