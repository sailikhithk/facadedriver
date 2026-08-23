# FacadeDriver Architecture

## Design goals

1. **Model-agnostic**: application code never references a model name.
2. **Zero-downtime swap**: change the backing model at runtime.
3. **Graceful degradation**: fall back automatically on failure.
4. **Observable**: every request emits cost, latency, and fallback telemetry.
5. **Pluggable**: backends, routers, and telemetry sinks are all protocols.
6. **Thin**: the orchestration layer adds ~20us per request (see benchmarks).

## Layer diagram

```
Application
    |
    v
FacadeDriver.generate(route, messages)
    |
    +-- Router: route -> [primary, *fallback] model chain
    |
    +-- for each model in chain:
    |     |
    |     +-- CircuitBreaker.allow(model)  -- skip if open
    |     |
    |     +-- Backend.generate(model, messages)
    |     |     |
    |     |     +-- RawSDKBackend  (openai / anthropic / google-genai)
    |     |     +-- LiteLLMBackend (litellm.completion)
    |     |     +-- MockBackend    (tests, demos)
    |     |     +-- custom plugin backends
    |     |
    |     +-- on success: CircuitBreaker.record_success -> return Response
    |     +-- on failure: retry (per route config)
    |                     then CircuitBreaker.record_failure -> next model
    |
    +-- TelemetrySink.emit(event)  -- structlog / file / prometheus / custom
    |
    v
Response (content, model, cost, latency, fallback_chain, request_id)
```

```mermaid
flowchart TD
    APP["Application<br/>driver.generate('summarize', messages)"]
    ROUTER["Router<br/>route name -> [primary, *fallback] model chain<br/>runtime swap (no code change)"]

    subgraph RT["Route table (YAML / dict)"]
        direction TB
        R1["route: summarize<br/>retry: 2, timeout: 30s"] --> R1P["primary: claude-3-5-sonnet"] --> R1F1["fallback 1: gpt-4o"] --> R1F2["fallback 2: llama-3.1-70b"]
        R2["route: code-review<br/>retry: 1, timeout: 60s"] --> R2P["primary: claude-3-5-sonnet"] --> R2F1["fallback 1: gemini-1.5-pro"] --> R2F2["fallback 2: gpt-4o-mini"]
        R3["route: cheap-chat<br/>retry: 3, timeout: 10s"] --> R3P["primary: gpt-4o-mini"] --> R3F1["fallback 1: llama-3.1-8b"] --> R3F2["fallback 2: mock"]
    end

    APP -->|"&quot;summarize&quot;"| ROUTER
    ROUTER --> R1
    ROUTER --> R2
    ROUTER --> R3

    style APP fill:#083344,stroke:#22d3ee,stroke-width:2px,color:#fff
    style ROUTER fill:#78350f,stroke:#fbbf24,stroke-width:2px,color:#fff
    style R1P fill:#064e3b,stroke:#34d399,color:#fff
    style R2P fill:#064e3b,stroke:#34d399,color:#fff
    style R3P fill:#064e3b,stroke:#34d399,color:#fff
    style R1F1 fill:#78350f,stroke:#fbbf24,color:#fff
    style R2F1 fill:#78350f,stroke:#fbbf24,color:#fff
    style R3F1 fill:#78350f,stroke:#fbbf24,color:#fff
    style R1F2 fill:#881337,stroke:#fb7185,color:#fff
    style R2F2 fill:#881337,stroke:#fb7185,color:#fff
    style R3F2 fill:#881337,stroke:#fb7185,color:#fff
```

_Routes, not models: a route is a stable name that maps to an ordered model chain; the call site never references a provider._

## Module layout

```
src/facadedriver/
  __init__.py        - public API exports
  types.py           - Response, Message, HealthStatus, error classes
  config.py          - typed Config, loaded from YAML or dict
  driver.py          - FacadeDriver class (sync + async)
  routing.py         - Router with runtime swap
  resilience.py      - CircuitBreaker (per-model state machine)
  telemetry.py       - TelemetrySink protocol, StructlogSink, FileSink
  backends/
    __init__.py      - Backend protocol, MockBackend, RawSDKBackend
    litellm.py       - LiteLLMBackend
  async_support.py   - AsyncBackend, AsyncMockBackend, AsyncRawSDKBackend
  cli.py             - facadedriver CLI
  server.py          - FastAPI server mode
  plugins.py         - plugin discovery and loading
  prometheus.py      - PrometheusSink + metrics server
```

```mermaid
flowchart TD
    CALLER["caller<br/>app code that imports facadedriver"]

    subgraph SYNC["Sync path"]
        S1["1. route lookup + circuit check (sync)"]
        S2["2. backend.generate(req) - blocks caller"]
        S3["3. validate + telemetry emit (sync)"]
        S1 --> S2 --> S3
    end

    subgraph ASYNC["Async path"]
        A1["1. route lookup + circuit check (sync, fast)"]
        A2["2. await backend.generate_async(req) - yields"]
        A3["3. validate + telemetry emit (sync, fast)"]
        A1 --> A2 --> A3
    end

    CORE["Shared driver core<br/>routing, circuit breaker, fallback chain, validators, telemetry<br/>one codepath; sync wraps async via anyio.to_thread.run_sync"]

    CALLER -->|"driver.generate(...)"| SYNC
    CALLER -->|"await driver.generate_async(...)"| ASYNC
    SYNC --> CORE
    ASYNC --> CORE

    style CALLER fill:#78350f,stroke:#fbbf24,stroke-width:2px,color:#fff
    style SYNC fill:#064e3b22,stroke:#34d399,stroke-width:2px
    style ASYNC fill:#08334422,stroke:#22d3ee,stroke-width:2px
    style CORE fill:#4c1d95,stroke:#a78bfa,stroke-width:2px,color:#fff
```

```mermaid
flowchart LR
    DRIVER["FacadeDriver<br/>construction: plugins=[...]"]

    subgraph HOOKS["Hook points (run in priority order)"]
        direction TB
        H1["hook: before_route<br/>(mutate request)"]
        H2["hook: after_route<br/>(inspect chosen model)"]
        H3["hook: before_backend<br/>(mutate req, retry)"]
        H4["hook: after_backend<br/>(validate, redact)"]
        H5["hook: on_fallback<br/>(log, alert, mutate)"]
        H6["hook: on_circuit_trip<br/>(notify)"]
        H7["hook: before_telemetry<br/>(scrub PII)"]
        H1 --> H2 --> H3 --> H4 --> H5 --> H6 --> H7
    end

    subgraph REG["PluginRegistry<br/>(ordered by priority)"]
        direction TB
        P1["PIIScrubberPlugin<br/>hooks: before_telemetry"]
        P2["RetryPlugin<br/>hooks: after_backend"]
        P3["CostBudgetPlugin<br/>hooks: before_route, after_backend"]
        P4["AuditLogPlugin<br/>hooks: on_fallback, on_circuit_trip"]
        P5["CustomPlugin ..."]
        P1 --> P2 --> P3 --> P4 --> P5
    end

    PROTO["Plugin (Protocol)<br/>@runtime_checkable<br/>name, priority, hooks<br/>default impls are no-ops"]

    DRIVER --> HOOKS
    REG -.->|dispatch| HOOKS
    HOOKS -.->|implement| PROTO

    style DRIVER fill:#78350f,stroke:#fbbf24,stroke-width:2px,color:#fff
    style REG fill:#4c1d9533,stroke:#a78bfa,stroke-width:2px
    style HOOKS fill:#88133722,stroke:#fb7185,stroke-width:2px
    style PROTO fill:#083344,stroke:#22d3ee,stroke-width:2px,color:#fff
```

_Async (left): same driver, two execution modes; sync blocks the caller, async yields control via anyio. Plugins (right): hook points at every stage; plugins register at construction and run in deterministic priority order - composable, isolated, and testable._

## Key design decisions

### Routes, not models

A route is a stable name (`"summarize"`, `"code-review"`) that maps to
a model chain. Application code uses route names. This decouples the
call site from the provider and model, enabling runtime swaps and
fallbacks without code changes.

```mermaid
flowchart TD
    REQ["driver.generate('summarize', messages)<br/>chain: [claude-3-5-sonnet, gpt-4o, llama-3.1-70b]"]

    S1["Step 1: primary<br/>claude-3-5-sonnet<br/>circuit: CLOSED<br/>timeout: 30s, retry: 2<br/>result: TIMEOUT"]
    S2["Step 2: fallback 1<br/>gpt-4o<br/>circuit: OPEN (skip)<br/>circuit_trip = true<br/>advance immediately"]
    S3["Step 3: fallback 2<br/>llama-3.1-70b<br/>circuit: CLOSED<br/>timeout: 30s, retry: 2<br/>result: SUCCESS"]

    RESP["Response<br/>content + metadata + provenance"]

    REQ --> S1
    S1 -->|timeout| S2
    S2 -->|skip| S3
    S3 -->|success| RESP

    style S1 fill:#881337,stroke:#fb7185,stroke-width:2px,color:#fff
    style S2 fill:#78350f,stroke:#fbbf24,stroke-width:2px,color:#fff
    style S3 fill:#064e3b,stroke:#34d399,stroke-width:2px,color:#fff
    style RESP fill:#064e3b,stroke:#34d399,stroke-width:2px,color:#fff
```

_Fallback chain: walk the chain top-to-bottom; on failure (timeout, error, hallucination flag), advance to the next model with full context. If every model fails, the driver raises FallbackExhausted with the full attempts list attached._

### Per-model circuit breaker

The circuit breaker is keyed by model, not by route. A model can
appear in multiple routes; its health is global. This prevents one
route from hammering a failing model while another route's breaker is
still closed.

```mermaid
stateDiagram-v2
    [*] --> CLOSED
    CLOSED --> OPEN : error_rate > threshold\nor hallucination flag
    OPEN --> HALF_OPEN : cooldown elapsed
    HALF_OPEN --> CLOSED : probe success\n(reset failure_count)
    HALF_OPEN --> OPEN : probe failure\n(cooldown restarts)

    note right of CLOSED
        requests flow normally
        success/failure_count tracked
        response.circuit_state = "closed"
    end note
    note right of OPEN
        requests short-circuited
        model skipped in chain
        response.circuit_trip = true
        fallback advances immediately
    end note
    note right of HALF_OPEN
        single probe request allowed
        success -> CLOSED
        failure -> OPEN
    end note
```

_Per-model circuit breaker: each model has its own state machine; health is global across every route that references it._

### Backend as protocol

`Backend` is a `runtime_checkable` Protocol with a single method:
`generate(model, messages, ...) -> BackendResponse`. Any object with
that method is a valid backend. This makes it trivial to add new
providers or wrap existing SDKs.

```mermaid
flowchart TD
    DRIVER["FacadeDriver<br/>calls backend.generate(req)"]
    PROTO["Backend (Protocol)<br/>@runtime_checkable<br/>def generate(req) -> Response<br/>def stream(req) -> Iterator[Chunk]<br/>def health() -> HealthStatus<br/>name: str, capabilities: set[Capability]"]

    ANTH["AnthropicBackend<br/>messages API<br/>prompt caching, streaming<br/>caps: {tools, vision}"]
    OPENAI["OpenAIBackend<br/>chat.completions<br/>function calling, json mode<br/>caps: {tools, json}"]
    GEM["GeminiBackend<br/>generateContent<br/>function declarations, multimodal<br/>caps: {tools, vision}"]
    OLLAMA["OllamaBackend<br/>/api/chat, local models<br/>streaming via NDJSON<br/>caps: {local}"]
    CUST["Custom<br/>implements Backend<br/>vLLM, TGI, internal API"]

    DRIVER --> PROTO
    PROTO --> ANTH
    PROTO --> OPENAI
    PROTO --> GEM
    PROTO --> OLLAMA
    PROTO --> CUST

    style DRIVER fill:#78350f,stroke:#fbbf24,stroke-width:2px,color:#fff
    style PROTO fill:#083344,stroke:#22d3ee,stroke-width:2px,color:#fff
    style ANTH fill:#064e3b,stroke:#34d399,color:#fff
    style OPENAI fill:#083344,stroke:#22d3ee,color:#fff
    style GEM fill:#78350f,stroke:#fbbf24,color:#fff
    style OLLAMA fill:#4c1d95,stroke:#a78bfa,color:#fff
    style CUST fill:#881337,stroke:#fb7185,color:#fff
```

_Backend as protocol: one Backend Protocol; many providers implement it; the driver never sees provider-specific shapes. Request and Response are provider-agnostic; each backend translates to/from its native format internally._

### Telemetry never breaks the request

The driver wraps `sink.emit()` in a try/except. A broken telemetry
sink (e.g. a full disk) must never cause a user-facing failure.

```mermaid
flowchart TD
    DRIVER["Driver.generate()<br/>single call site<br/>emits one TelemetryEvent"]
    EVT["TelemetryEvent<br/>route, model_used, latency_ms<br/>attempts, circuit_state, circuit_trip<br/>prompt_hash, tokens_in, tokens_out<br/>hallucination_flag, error_class"]
    BUS["TelemetrySink (fan-out bus)<br/>each sink implements .emit(event) -> None<br/>failures are isolated"]

    CONSOLE["ConsoleSink<br/>stdout (dev), pretty JSON"]
    OTEL["OTelSink<br/>OpenTelemetry<br/>span per attempt"]
    LANG["LangfuseSink<br/>generation + span<br/>prompt + completion"]
    FILE["FileSink<br/>JSONL file, rotated daily"]
    CUSTOM["Custom<br/>plugin sink<br/>user-defined"]

    DRIVER --> EVT
    EVT --> BUS
    BUS --> CONSOLE
    BUS --> OTEL
    BUS --> LANG
    BUS --> FILE
    BUS --> CUSTOM

    style DRIVER fill:#78350f,stroke:#fbbf24,stroke-width:2px,color:#fff
    style EVT fill:#083344,stroke:#22d3ee,stroke-width:2px,color:#fff
    style BUS fill:#4c1d95,stroke:#a78bfa,stroke-width:2px,color:#fff
    style CONSOLE fill:#064e3b,stroke:#34d399,color:#fff
    style OTEL fill:#083344,stroke:#22d3ee,color:#fff
    style LANG fill:#78350f,stroke:#fbbf24,color:#fff
    style FILE fill:#881337,stroke:#fb7185,color:#fff
    style CUSTOM fill:#4c1d95,stroke:#a78bfa,color:#fff
```

_Telemetry sink fan-out: one event, many sinks; the driver emits once and each sink formats for its destination. Sink failures are caught and logged; a broken sink must not break the user's generation request._

### Lazy SDK imports

Provider SDKs (openai, anthropic, google-genai, litellm) are imported
lazily inside the backend call, not at module load time. This means
you can install FacadeDriver and use MockBackend without any provider
SDK installed. The ImportError message tells you exactly what to pip
install.

## Failure modes

| Failure             | Behavior                                           |
|---------------------|----------------------------------------------------|
| Primary model 500s  | Retry per route config, then fall back to next     |
| All models fail     | Raise `AllProvidersFailedError` with chain + errors|
| Circuit open        | Skip model, go to next in chain, set `circuit_trip`|
| Telemetry sink dies | Swallow exception, continue serving                |
| Route not found     | Raise `RouteNotFoundError`                         |

## Performance

From `benchmarks/bench_overhead.py` on a 2024 MacBook:

| Suite                          | Median   | p95      |
|--------------------------------|----------|----------|
| raw MockBackend.generate()     | 3.1us    | 5.1us    |
| FacadeDriver (null sink)       | 19.7us   | 29.6us   |
| FacadeDriver (structlog sink)  | 38.7us   | 70.7us   |
| FacadeDriver (with fallback)   | 21.5us   | 27.6us   |
| Async throughput               | 31,284 req/sec      |

For real LLM calls (100ms-10s), the ~20us overhead is negligible
(<0.01%).
