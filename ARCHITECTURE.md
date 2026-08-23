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

<details>
<summary>Visual companion diagram (inline)</summary>

<svg viewBox="0 0 1000 620">
        <defs>
          <marker id="01_routing__arrow" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#64748b" />
          </marker>
          <marker id="01_routing__arrow-cyan" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#22d3ee" />
          </marker>
          <marker id="01_routing__arrow-emerald" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#34d399" />
          </marker>
          <marker id="01_routing__arrow-amber" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#fbbf24" />
          </marker>
          <pattern id="01_routing__grid" width="40" height="40" patternUnits="userSpaceOnUse">
            <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#1e293b" stroke-width="0.5"/>
          </pattern>
        </defs>

        <rect width="100%" height="100%" fill="url(#01_routing__grid)" />

        <!-- Application call site -->
        <rect x="370" y="40" width="260" height="60" rx="8" fill="rgba(8, 51, 68, 0.4)" stroke="#22d3ee" stroke-width="1.5"/>
        <text x="500" y="64" fill="white" font-size="12" font-weight="600" text-anchor="middle">Application</text>
        <text x="500" y="82" fill="#94a3b8" font-size="9" text-anchor="middle">driver.generate("summarize", messages)</text>

        <!-- Router core -->
        <rect x="330" y="140" width="340" height="80" rx="10" fill="rgba(120, 53, 15, 0.3)" stroke="#fbbf24" stroke-width="2"/>
        <text x="500" y="166" fill="white" font-size="13" font-weight="700" text-anchor="middle">Router</text>
        <text x="500" y="184" fill="#94a3b8" font-size="9" text-anchor="middle">route name -> [primary, *fallback] model chain</text>
        <text x="500" y="200" fill="#fbbf24" font-size="8" text-anchor="middle">runtime swap (no code change)</text>

        <!-- Route table -->
        <rect x="60" y="270" width="880" height="240" rx="10" fill="rgba(15, 23, 42, 0.5)" stroke="#1e293b" stroke-width="1.5"/>
        <text x="80" y="296" fill="white" font-size="11" font-weight="600">Route table (YAML / dict)</text>
        <text x="80" y="312" fill="#94a3b8" font-size="8">stable names -> ordered model chains</text>

        <!-- Route: summarize -->
        <rect x="80" y="330" width="260" height="160" rx="8" fill="rgba(8, 51, 68, 0.4)" stroke="#22d3ee" stroke-width="1.5"/>
        <text x="210" y="354" fill="white" font-size="11" font-weight="600" text-anchor="middle">route: "summarize"</text>
        <text x="210" y="370" fill="#94a3b8" font-size="8" text-anchor="middle">retry: 2, timeout: 30s</text>

        <rect x="100" y="384" width="220" height="28" rx="4" fill="rgba(6, 78, 59, 0.4)" stroke="#34d399" stroke-width="1"/>
        <text x="210" y="402" fill="white" font-size="9" text-anchor="middle">primary: claude-3-5-sonnet</text>

        <rect x="100" y="418" width="220" height="28" rx="4" fill="rgba(120, 53, 15, 0.3)" stroke="#fbbf24" stroke-width="1"/>
        <text x="210" y="436" fill="white" font-size="9" text-anchor="middle">fallback 1: gpt-4o</text>

        <rect x="100" y="452" width="220" height="28" rx="4" fill="rgba(136, 19, 55, 0.4)" stroke="#fb7185" stroke-width="1"/>
        <text x="210" y="470" fill="white" font-size="9" text-anchor="middle">fallback 2: llama-3.1-70b</text>

        <!-- Route: code-review -->
        <rect x="370" y="330" width="260" height="160" rx="8" fill="rgba(8, 51, 68, 0.4)" stroke="#22d3ee" stroke-width="1.5"/>
        <text x="500" y="354" fill="white" font-size="11" font-weight="600" text-anchor="middle">route: "code-review"</text>
        <text x="500" y="370" fill="#94a3b8" font-size="8" text-anchor="middle">retry: 1, timeout: 60s</text>

        <rect x="390" y="384" width="220" height="28" rx="4" fill="rgba(6, 78, 59, 0.4)" stroke="#34d399" stroke-width="1"/>
        <text x="500" y="402" fill="white" font-size="9" text-anchor="middle">primary: claude-3-5-sonnet</text>

        <rect x="390" y="418" width="220" height="28" rx="4" fill="rgba(120, 53, 15, 0.3)" stroke="#fbbf24" stroke-width="1"/>
        <text x="500" y="436" fill="white" font-size="9" text-anchor="middle">fallback 1: gemini-1.5-pro</text>

        <rect x="390" y="452" width="220" height="28" rx="4" fill="rgba(136, 19, 55, 0.4)" stroke="#fb7185" stroke-width="1"/>
        <text x="500" y="470" fill="white" font-size="9" text-anchor="middle">fallback 2: gpt-4o-mini</text>

        <!-- Route: cheap-chat -->
        <rect x="660" y="330" width="260" height="160" rx="8" fill="rgba(8, 51, 68, 0.4)" stroke="#22d3ee" stroke-width="1.5"/>
        <text x="790" y="354" fill="white" font-size="11" font-weight="600" text-anchor="middle">route: "cheap-chat"</text>
        <text x="790" y="370" fill="#94a3b8" font-size="8" text-anchor="middle">retry: 3, timeout: 10s</text>

        <rect x="680" y="384" width="220" height="28" rx="4" fill="rgba(6, 78, 59, 0.4)" stroke="#34d399" stroke-width="1"/>
        <text x="790" y="402" fill="white" font-size="9" text-anchor="middle">primary: gpt-4o-mini</text>

        <rect x="680" y="418" width="220" height="28" rx="4" fill="rgba(120, 53, 15, 0.3)" stroke="#fbbf24" stroke-width="1"/>
        <text x="790" y="436" fill="white" font-size="9" text-anchor="middle">fallback 1: llama-3.1-8b</text>

        <rect x="680" y="452" width="220" height="28" rx="4" fill="rgba(136, 19, 55, 0.4)" stroke="#fb7185" stroke-width="1"/>
        <text x="790" y="470" fill="white" font-size="9" text-anchor="middle">fallback 2: mock</text>

        <!-- Arrows -->
        <line x1="500" y1="100" x2="500" y2="138" stroke="#22d3ee" stroke-width="1.5" marker-end="url(#01_routing__arrow-cyan)"/>
        <text x="514" y="124" fill="#94a3b8" font-size="8">"summarize"</text>

        <line x1="500" y1="220" x2="210" y2="328" stroke="#fbbf24" stroke-width="1.5" marker-end="url(#01_routing__arrow-amber)"/>
        <line x1="500" y1="220" x2="500" y2="328" stroke="#fbbf24" stroke-width="1.5" marker-end="url(#01_routing__arrow-amber)"/>
        <line x1="500" y1="220" x2="790" y2="328" stroke="#fbbf24" stroke-width="1.5" marker-end="url(#01_routing__arrow-amber)"/>

        <!-- Chain order arrows (vertical within each route) -->
        <line x1="210" y1="412" x2="210" y2="416" stroke="#34d399" stroke-width="1" marker-end="url(#01_routing__arrow-emerald)"/>
        <line x1="210" y1="446" x2="210" y2="450" stroke="#fbbf24" stroke-width="1" marker-end="url(#01_routing__arrow-amber)"/>
        <line x1="500" y1="412" x2="500" y2="416" stroke="#34d399" stroke-width="1" marker-end="url(#01_routing__arrow-emerald)"/>
        <line x1="500" y1="446" x2="500" y2="450" stroke="#fbbf24" stroke-width="1" marker-end="url(#01_routing__arrow-amber)"/>
        <line x1="790" y1="412" x2="790" y2="416" stroke="#34d399" stroke-width="1" marker-end="url(#01_routing__arrow-emerald)"/>
        <line x1="790" y1="446" x2="790" y2="450" stroke="#fbbf24" stroke-width="1" marker-end="url(#01_routing__arrow-amber)"/>

        <!-- Legend -->
        <text x="60" y="540" fill="white" font-size="10" font-weight="600">Legend</text>
        <rect x="60" y="552" width="16" height="10" rx="2" fill="rgba(6, 78, 59, 0.4)" stroke="#34d399" stroke-width="1"/>
        <text x="82" y="560" fill="#94a3b8" font-size="8">primary model</text>
        <rect x="180" y="552" width="16" height="10" rx="2" fill="rgba(120, 53, 15, 0.3)" stroke="#fbbf24" stroke-width="1"/>
        <text x="202" y="560" fill="#94a3b8" font-size="8">fallback model</text>
        <rect x="300" y="552" width="16" height="10" rx="2" fill="rgba(136, 19, 55, 0.4)" stroke="#fb7185" stroke-width="1"/>
        <text x="322" y="560" fill="#94a3b8" font-size="8">last-resort fallback</text>

        <text x="60" y="585" fill="#94a3b8" font-size="8">Why: decouples call site from provider -> runtime swaps + fallbacks without code changes.</text>
        <text x="60" y="600" fill="#94a3b8" font-size="8">A model can appear in many routes; its circuit-breaker health is global (see 02-circuit-breaker).</text>
      </svg>

</details>

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

<details>
<summary>Visual companion diagram (inline)</summary>

<svg viewBox="0 0 1000 620">
        <defs>
          <marker id="06_async__arrow-emerald" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#34d399" />
          </marker>
          <marker id="06_async__arrow-cyan" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#22d3ee" />
          </marker>
          <marker id="06_async__arrow-amber" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#fbbf24" />
          </marker>
          <marker id="06_async__arrow-violet" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#a78bfa" />
          </marker>
          <pattern id="06_async__grid" width="40" height="40" patternUnits="userSpaceOnUse">
            <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#1e293b" stroke-width="0.5"/>
          </pattern>
        </defs>

        <rect width="100%" height="100%" fill="url(#06_async__grid)" />

        <!-- Caller -->
        <rect x="380" y="30" width="240" height="50" rx="8" fill="rgba(120, 53, 15, 0.3)" stroke="#fbbf24" stroke-width="2"/>
        <text x="500" y="50" fill="white" font-size="11" font-weight="600" text-anchor="middle">caller</text>
        <text x="500" y="66" fill="#94a3b8" font-size="8" text-anchor="middle">app code that imports facadedriver</text>

        <!-- Sync path -->
        <rect x="60" y="120" width="400" height="220" rx="10" fill="rgba(6, 78, 59, 0.3)" stroke="#34d399" stroke-width="2"/>
        <text x="260" y="146" fill="white" font-size="13" font-weight="700" text-anchor="middle">Sync path</text>
        <text x="260" y="164" fill="#34d399" font-size="9" text-anchor="middle">driver.generate(...)</text>

        <rect x="80" y="180" width="360" height="40" rx="6" fill="rgba(15, 23, 42, 0.5)" stroke="#1e293b" stroke-width="1"/>
        <text x="100" y="204" fill="white" font-size="9">1. route lookup + circuit check (sync)</text>

        <rect x="80" y="230" width="360" height="40" rx="6" fill="rgba(15, 23, 42, 0.5)" stroke="#1e293b" stroke-width="1"/>
        <text x="100" y="254" fill="white" font-size="9">2. backend.generate(req) - blocks caller</text>

        <rect x="80" y="280" width="360" height="40" rx="6" fill="rgba(15, 23, 42, 0.5)" stroke="#1e293b" stroke-width="1"/>
        <text x="100" y="304" fill="white" font-size="9">3. validate + telemetry emit (sync)</text>

        <text x="260" y="334" fill="#94a3b8" font-size="8" text-anchor="middle">returns Response; caller thread blocked for latency_ms</text>

        <!-- Async path -->
        <rect x="540" y="120" width="400" height="220" rx="10" fill="rgba(8, 51, 68, 0.3)" stroke="#22d3ee" stroke-width="2"/>
        <text x="740" y="146" fill="white" font-size="13" font-weight="700" text-anchor="middle">Async path</text>
        <text x="740" y="164" fill="#22d3ee" font-size="9" text-anchor="middle">await driver.generate_async(...)</text>

        <rect x="560" y="180" width="360" height="40" rx="6" fill="rgba(15, 23, 42, 0.5)" stroke="#1e293b" stroke-width="1"/>
        <text x="580" y="204" fill="white" font-size="9">1. route lookup + circuit check (sync, fast)</text>

        <rect x="560" y="230" width="360" height="40" rx="6" fill="rgba(15, 23, 42, 0.5)" stroke="#1e293b" stroke-width="1"/>
        <text x="580" y="254" fill="white" font-size="9">2. await backend.generate_async(req) - yields</text>

        <rect x="560" y="280" width="360" height="40" rx="6" fill="rgba(15, 23, 42, 0.5)" stroke="#1e293b" stroke-width="1"/>
        <text x="580" y="304" fill="white" font-size="9">3. validate + telemetry emit (sync, fast)</text>

        <text x="740" y="334" fill="#94a3b8" font-size="8" text-anchor="middle">returns Response; event loop free during network wait</text>

        <!-- Arrows from caller -->
        <path d="M 440 80 Q 300 100 260 118" fill="none" stroke="#34d399" stroke-width="2" marker-end="url(#06_async__arrow-emerald)"/>
        <path d="M 560 80 Q 700 100 740 118" fill="none" stroke="#22d3ee" stroke-width="2" marker-end="url(#06_async__arrow-cyan)"/>

        <!-- Shared core -->
        <rect x="200" y="380" width="600" height="80" rx="10" fill="rgba(76, 29, 149, 0.3)" stroke="#a78bfa" stroke-width="2"/>
        <text x="500" y="406" fill="white" font-size="12" font-weight="700" text-anchor="middle">Shared driver core</text>
        <text x="500" y="424" fill="#a78bfa" font-size="9" text-anchor="middle">routing, circuit breaker, fallback chain, validators, telemetry</text>
        <text x="500" y="440" fill="#94a3b8" font-size="8" text-anchor="middle">one codepath; sync wraps async via anyio.to_thread.run_sync</text>
        <text x="500" y="454" fill="#94a3b8" font-size="8" text-anchor="middle">async wraps sync via anyio.from_thread.run_sync</text>

        <path d="M 260 340 L 400 378" fill="none" stroke="#a78bfa" stroke-width="1.5" marker-end="url(#06_async__arrow-violet)"/>
        <path d="M 740 340 L 600 378" fill="none" stroke="#a78bfa" stroke-width="1.5" marker-end="url(#06_async__arrow-violet)"/>

        <!-- Backend dual mode -->
        <rect x="60" y="500" width="880" height="100" rx="10" fill="rgba(15, 23, 42, 0.5)" stroke="#1e293b" stroke-width="1.5"/>
        <text x="80" y="526" fill="white" font-size="11" font-weight="600">Backend contract (both modes)</text>

        <rect x="80" y="540" width="420" height="40" rx="6" fill="rgba(6, 78, 59, 0.4)" stroke="#34d399" stroke-width="1"/>
        <text x="100" y="564" fill="white" font-size="9">def generate(self, req) -> Response</text>

        <rect x="520" y="540" width="420" height="40" rx="6" fill="rgba(8, 51, 68, 0.4)" stroke="#22d3ee" stroke-width="1"/>
        <text x="540" y="564" fill="white" font-size="9">async def generate_async(self, req) -> Response</text>

        <text x="60" y="600" fill="#94a3b8" font-size="8">Why anyio (not asyncio): backend-agnostic - works on asyncio, trio, curio; tests can swap sync/async without rewriting.</text>
        <text x="60" y="614" fill="#94a3b8" font-size="8">Streaming uses async iterators in both modes; sync callers consume via next() on a wrapped generator.</text>
      </svg>

</details>
<details>
<summary>Visual companion diagram (inline)</summary>

<svg viewBox="0 0 1000 640">
        <defs>
          <marker id="07_plugins__arrow-rose" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#fb7185" />
          </marker>
          <marker id="07_plugins__arrow-cyan" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#22d3ee" />
          </marker>
          <marker id="07_plugins__arrow-amber" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#fbbf24" />
          </marker>
          <marker id="07_plugins__arrow-violet" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#a78bfa" />
          </marker>
          <marker id="07_plugins__arrow-emerald" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#34d399" />
          </marker>
          <pattern id="07_plugins__grid" width="40" height="40" patternUnits="userSpaceOnUse">
            <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#1e293b" stroke-width="0.5"/>
          </pattern>
        </defs>

        <rect width="100%" height="100%" fill="url(#07_plugins__grid)" />

        <!-- Driver pipeline (center) -->
        <rect x="380" y="30" width="240" height="50" rx="8" fill="rgba(120, 53, 15, 0.3)" stroke="#fbbf24" stroke-width="2"/>
        <text x="500" y="50" fill="white" font-size="11" font-weight="600" text-anchor="middle">FacadeDriver</text>
        <text x="500" y="66" fill="#94a3b8" font-size="8" text-anchor="middle">construction: plugins=[...]</text>

        <!-- Hook points (vertical pipeline) -->
        <rect x="350" y="110" width="300" height="40" rx="6" fill="rgba(15, 23, 42, 0.5)" stroke="#fb7185" stroke-width="1.5"/>
        <text x="500" y="134" fill="white" font-size="10" text-anchor="middle">hook: before_route (mutate request)</text>

        <rect x="350" y="160" width="300" height="40" rx="6" fill="rgba(15, 23, 42, 0.5)" stroke="#fb7185" stroke-width="1.5"/>
        <text x="500" y="184" fill="white" font-size="10" text-anchor="middle">hook: after_route (inspect chosen model)</text>

        <rect x="350" y="210" width="300" height="40" rx="6" fill="rgba(15, 23, 42, 0.5)" stroke="#fb7185" stroke-width="1.5"/>
        <text x="500" y="234" fill="white" font-size="10" text-anchor="middle">hook: before_backend (mutate req, retry)</text>

        <rect x="350" y="260" width="300" height="40" rx="6" fill="rgba(15, 23, 42, 0.5)" stroke="#fb7185" stroke-width="1.5"/>
        <text x="500" y="284" fill="white" font-size="10" text-anchor="middle">hook: after_backend (validate, redact)</text>

        <rect x="350" y="310" width="300" height="40" rx="6" fill="rgba(15, 23, 42, 0.5)" stroke="#fb7185" stroke-width="1.5"/>
        <text x="500" y="334" fill="white" font-size="10" text-anchor="middle">hook: on_fallback (log, alert, mutate)</text>

        <rect x="350" y="360" width="300" height="40" rx="6" fill="rgba(15, 23, 42, 0.5)" stroke="#fb7185" stroke-width="1.5"/>
        <text x="500" y="384" fill="white" font-size="10" text-anchor="middle">hook: on_circuit_trip (notify)</text>

        <rect x="350" y="410" width="300" height="40" rx="6" fill="rgba(15, 23, 42, 0.5)" stroke="#fb7185" stroke-width="1.5"/>
        <text x="500" y="434" fill="white" font-size="10" text-anchor="middle">hook: before_telemetry (scrub PII)</text>

        <path d="M 500 80 L 500 108" fill="none" stroke="#fb7185" stroke-width="1.5" marker-end="url(#07_plugins__arrow-rose)"/>

        <!-- Plugin registry (left) -->
        <rect x="40" y="110" width="240" height="340" rx="10" fill="rgba(76, 29, 149, 0.3)" stroke="#a78bfa" stroke-width="2"/>
        <text x="160" y="136" fill="white" font-size="12" font-weight="700" text-anchor="middle">PluginRegistry</text>
        <text x="160" y="154" fill="#a78bfa" font-size="8" text-anchor="middle">ordered by registration priority</text>

        <rect x="60" y="170" width="200" height="50" rx="6" fill="rgba(15, 23, 42, 0.5)" stroke="#1e293b" stroke-width="1"/>
        <text x="160" y="190" fill="white" font-size="9" text-anchor="middle">PIIScrubberPlugin</text>
        <text x="160" y="206" fill="#94a3b8" font-size="8" text-anchor="middle">hooks: before_telemetry</text>

        <rect x="60" y="230" width="200" height="50" rx="6" fill="rgba(15, 23, 42, 0.5)" stroke="#1e293b" stroke-width="1"/>
        <text x="160" y="250" fill="white" font-size="9" text-anchor="middle">RetryPlugin</text>
        <text x="160" y="266" fill="#94a3b8" font-size="8" text-anchor="middle">hooks: after_backend</text>

        <rect x="60" y="290" width="200" height="50" rx="6" fill="rgba(15, 23, 42, 0.5)" stroke="#1e293b" stroke-width="1"/>
        <text x="160" y="310" fill="white" font-size="9" text-anchor="middle">CostBudgetPlugin</text>
        <text x="160" y="326" fill="#94a3b8" font-size="8" text-anchor="middle">hooks: before_route, after_backend</text>

        <rect x="60" y="350" width="200" height="50" rx="6" fill="rgba(15, 23, 42, 0.5)" stroke="#1e293b" stroke-width="1"/>
        <text x="160" y="370" fill="white" font-size="9" text-anchor="middle">AuditLogPlugin</text>
        <text x="160" y="386" fill="#94a3b8" font-size="8" text-anchor="middle">hooks: on_fallback, on_circuit_trip</text>

        <rect x="60" y="410" width="200" height="30" rx="6" fill="rgba(15, 23, 42, 0.5)" stroke="#1e293b" stroke-width="1"/>
        <text x="160" y="430" fill="white" font-size="9" text-anchor="middle">CustomPlugin ...</text>

        <!-- Arrows from registry to hooks -->
        <path d="M 300 195 Q 320 130 348 130" fill="none" stroke="#a78bfa" stroke-width="1" marker-end="url(#07_plugins__arrow-violet)"/>
        <path d="M 300 255 Q 320 280 348 280" fill="none" stroke="#a78bfa" stroke-width="1" marker-end="url(#07_plugins__arrow-violet)"/>
        <path d="M 300 315 Q 320 130 348 130" fill="none" stroke="#a78bfa" stroke-width="1" marker-end="url(#07_plugins__arrow-violet)"/>
        <path d="M 300 315 Q 320 280 348 280" fill="none" stroke="#a78bfa" stroke-width="1" marker-end="url(#07_plugins__arrow-violet)"/>
        <path d="M 300 375 Q 320 330 348 330" fill="none" stroke="#a78bfa" stroke-width="1" marker-end="url(#07_plugins__arrow-violet)"/>
        <path d="M 300 375 Q 320 380 348 380" fill="none" stroke="#a78bfa" stroke-width="1" marker-end="url(#07_plugins__arrow-violet)"/>

        <!-- Plugin protocol (right) -->
        <rect x="720" y="110" width="240" height="340" rx="10" fill="rgba(8, 51, 68, 0.3)" stroke="#22d3ee" stroke-width="2"/>
        <text x="840" y="136" fill="white" font-size="12" font-weight="700" text-anchor="middle">Plugin (Protocol)</text>
        <text x="840" y="154" fill="#22d3ee" font-size="8" text-anchor="middle">@runtime_checkable</text>

        <text x="740" y="180" fill="white" font-size="9">name: str</text>
        <text x="740" y="198" fill="white" font-size="9">priority: int = 100</text>
        <text x="740" y="216" fill="#94a3b8" font-size="8">hooks: set[HookPoint]</text>

        <text x="740" y="246" fill="#34d399" font-size="9">def before_route(ctx): ...</text>
        <text x="740" y="264" fill="#94a3b8" font-size="8">return None or mutated Request</text>

        <text x="740" y="290" fill="#34d399" font-size="9">def after_backend(ctx): ...</text>
        <text x="740" y="308" fill="#94a3b8" font-size="8">return None or Response</text>

        <text x="740" y="334" fill="#34d399" font-size="9">def on_fallback(ctx): ...</text>
        <text x="740" y="352" fill="#94a3b8" font-size="8">side effects only</text>

        <text x="740" y="378" fill="#34d399" font-size="9">def on_circuit_trip(ctx): ...</text>
        <text x="740" y="396" fill="#94a3b8" font-size="8">side effects only</text>

        <text x="740" y="422" fill="#fbbf24" font-size="8">default impls are no-ops;</text>
        <text x="740" y="436" fill="#fbbf24" font-size="8">plugins override only what they need</text>

        <!-- Arrows from hooks to plugin protocol -->
        <path d="M 650 130 Q 680 200 718 240" fill="none" stroke="#22d3ee" stroke-width="1" marker-end="url(#07_plugins__arrow-cyan)"/>
        <path d="M 650 280 Q 680 290 718 290" fill="none" stroke="#22d3ee" stroke-width="1" marker-end="url(#07_plugins__arrow-cyan)"/>
        <path d="M 650 330 Q 680 330 718 334" fill="none" stroke="#22d3ee" stroke-width="1" marker-end="url(#07_plugins__arrow-cyan)"/>
        <path d="M 650 380 Q 680 380 718 378" fill="none" stroke="#22d3ee" stroke-width="1" marker-end="url(#07_plugins__arrow-cyan)"/>

        <!-- Footer notes -->
        <rect x="40" y="480" width="920" height="140" rx="10" fill="rgba(15, 23, 42, 0.5)" stroke="#1e293b" stroke-width="1.5"/>
        <text x="60" y="506" fill="white" font-size="10" font-weight="600">Why plugins, not subclasses:</text>
        <text x="60" y="524" fill="#94a3b8" font-size="8">- Subclassing forces one customization axis; plugins compose - PII scrubber + cost budget + audit log all stack.</text>
        <text x="60" y="540" fill="#94a3b8" font-size="8">- Plugins are isolated; a buggy plugin can be removed without touching driver code or other plugins.</text>
        <text x="60" y="556" fill="#94a3b8" font-size="8">- Hooks run in priority order; deterministic, testable, no hidden ordering bugs.</text>
        <text x="60" y="572" fill="#94a3b8" font-size="8">- A plugin can short-circuit a hook (return a Response) to implement caching, guardrails, or mock backends.</text>
        <text x="60" y="588" fill="#94a3b8" font-size="8">- Tests inject a RecordingPlugin to assert on the exact hook sequence and payloads.</text>
        <text x="60" y="604" fill="#94a3b8" font-size="8">- Third-party plugins are loaded via entry points; no fork required to extend the driver.</text>
      </svg>

</details>

## Key design decisions

### Routes, not models

A route is a stable name (`"summarize"`, `"code-review"`) that maps to
a model chain. Application code uses route names. This decouples the
call site from the provider and model, enabling runtime swaps and
fallbacks without code changes.

<details>
<summary>Visual companion diagram (inline)</summary>

<svg viewBox="0 0 1000 660">
        <defs>
          <marker id="03_fallback_chain__arrow-emerald" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#34d399" />
          </marker>
          <marker id="03_fallback_chain__arrow-amber" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#fbbf24" />
          </marker>
          <marker id="03_fallback_chain__arrow-rose" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#fb7185" />
          </marker>
          <marker id="03_fallback_chain__arrow-cyan" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#22d3ee" />
          </marker>
          <pattern id="03_fallback_chain__grid" width="40" height="40" patternUnits="userSpaceOnUse">
            <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#1e293b" stroke-width="0.5"/>
          </pattern>
        </defs>

        <rect width="100%" height="100%" fill="url(#03_fallback_chain__grid)" />

        <!-- Request entry -->
        <rect x="370" y="30" width="260" height="50" rx="8" fill="rgba(8, 51, 68, 0.4)" stroke="#22d3ee" stroke-width="1.5"/>
        <text x="500" y="50" fill="white" font-size="11" font-weight="600" text-anchor="middle">driver.generate("summarize", messages)</text>
        <text x="500" y="66" fill="#94a3b8" font-size="8" text-anchor="middle">chain: [claude-3-5-sonnet, gpt-4o, llama-3.1-70b]</text>

        <!-- Step 1: primary -->
        <rect x="60" y="120" width="280" height="120" rx="10" fill="rgba(6, 78, 59, 0.4)" stroke="#34d399" stroke-width="2"/>
        <text x="200" y="146" fill="white" font-size="12" font-weight="700" text-anchor="middle">Step 1: primary</text>
        <text x="200" y="164" fill="#34d399" font-size="9" text-anchor="middle">claude-3-5-sonnet</text>
        <text x="200" y="184" fill="#94a3b8" font-size="8" text-anchor="middle">check circuit: CLOSED</text>
        <text x="200" y="200" fill="#94a3b8" font-size="8" text-anchor="middle">timeout: 30s, retry: 2</text>
        <text x="200" y="218" fill="#fb7185" font-size="8" text-anchor="middle">result: TIMEOUT</text>

        <!-- Step 2: fallback 1 -->
        <rect x="360" y="120" width="280" height="120" rx="10" fill="rgba(120, 53, 15, 0.3)" stroke="#fbbf24" stroke-width="2"/>
        <text x="500" y="146" fill="white" font-size="12" font-weight="700" text-anchor="middle">Step 2: fallback 1</text>
        <text x="500" y="164" fill="#fbbf24" font-size="9" text-anchor="middle">gpt-4o</text>
        <text x="500" y="184" fill="#94a3b8" font-size="8" text-anchor="middle">check circuit: OPEN (skip)</text>
        <text x="500" y="200" fill="#94a3b8" font-size="8" text-anchor="middle">circuit_trip = true</text>
        <text x="500" y="218" fill="#fb7185" font-size="8" text-anchor="middle">advance immediately</text>

        <!-- Step 3: fallback 2 -->
        <rect x="660" y="120" width="280" height="120" rx="10" fill="rgba(136, 19, 55, 0.4)" stroke="#fb7185" stroke-width="2"/>
        <text x="800" y="146" fill="white" font-size="12" font-weight="700" text-anchor="middle">Step 3: fallback 2</text>
        <text x="800" y="164" fill="#fb7185" font-size="9" text-anchor="middle">llama-3.1-70b</text>
        <text x="800" y="184" fill="#94a3b8" font-size="8" text-anchor="middle">check circuit: CLOSED</text>
        <text x="800" y="200" fill="#94a3b8" font-size="8" text-anchor="middle">timeout: 30s, retry: 2</text>
        <text x="800" y="218" fill="#34d399" font-size="8" text-anchor="middle">result: SUCCESS</text>

        <!-- Arrows between steps -->
        <path d="M 340 180 L 358 180" fill="none" stroke="#fb7185" stroke-width="2" marker-end="url(#03_fallback_chain__arrow-rose)"/>
        <text x="349" y="172" fill="#fb7185" font-size="7" text-anchor="middle">timeout</text>

        <path d="M 640 180 L 658 180" fill="none" stroke="#fbbf24" stroke-width="2" marker-end="url(#03_fallback_chain__arrow-amber)"/>
        <text x="649" y="172" fill="#fbbf24" font-size="7" text-anchor="middle">skip</text>

        <!-- Response -->
        <rect x="370" y="280" width="260" height="60" rx="8" fill="rgba(6, 78, 59, 0.4)" stroke="#34d399" stroke-width="2"/>
        <text x="500" y="304" fill="white" font-size="11" font-weight="600" text-anchor="middle">Response</text>
        <text x="500" y="322" fill="#34d399" font-size="9" text-anchor="middle">content + metadata + provenance</text>

        <path d="M 800 240 Q 800 270 500 270 Q 500 270 500 278" fill="none" stroke="#34d399" stroke-width="2" marker-end="url(#03_fallback_chain__arrow-emerald)"/>

        <!-- Metadata block -->
        <rect x="60" y="370" width="880" height="180" rx="10" fill="rgba(15, 23, 42, 0.5)" stroke="#1e293b" stroke-width="1.5"/>
        <text x="80" y="396" fill="white" font-size="11" font-weight="600">Response.metadata</text>
        <text x="80" y="412" fill="#94a3b8" font-size="8">caller sees which model produced the answer and which were skipped</text>

        <rect x="80" y="430" width="840" height="40" rx="6" fill="rgba(6, 78, 59, 0.4)" stroke="#34d399" stroke-width="1"/>
        <text x="100" y="454" fill="white" font-size="9" font-weight="600">model_used: llama-3.1-70b</text>
        <text x="350" y="454" fill="#94a3b8" font-size="9">route: summarize</text>
        <text x="550" y="454" fill="#94a3b8" font-size="9">attempts: 2</text>
        <text x="720" y="454" fill="#94a3b8" font-size="9">latency_ms: 4231</text>

        <rect x="80" y="478" width="840" height="40" rx="6" fill="rgba(120, 53, 15, 0.3)" stroke="#fbbf24" stroke-width="1"/>
        <text x="100" y="502" fill="white" font-size="9" font-weight="600">skipped: [gpt-4o (circuit OPEN)]</text>
        <text x="400" y="502" fill="#94a3b8" font-size="9">fallback_chain_depth: 2</text>
        <text x="650" y="502" fill="#94a3b8" font-size="9">circuit_trips: 1</text>

        <rect x="80" y="526" width="840" height="20" rx="6" fill="rgba(136, 19, 55, 0.4)" stroke="#fb7185" stroke-width="1"/>
        <text x="100" y="540" fill="white" font-size="9" font-weight="600">failed: [claude-3-5-sonnet (TIMEOUT)]</text>

        <text x="60" y="590" fill="#94a3b8" font-size="8">Why chain (not parallel): full context travels with each attempt; the fallback sees the same prompt + system message the primary saw.</text>
        <text x="60" y="604" fill="#94a3b8" font-size="8">Hallucination flag from the response validator counts as a failure and triggers advance, just like a timeout or HTTP error.</text>
        <text x="60" y="618" fill="#94a3b8" font-size="8">If every model fails, the driver raises FallbackExhausted with the full attempts list attached for debugging.</text>
      </svg>

</details>

### Per-model circuit breaker

The circuit breaker is keyed by model, not by route. A model can
appear in multiple routes; its health is global. This prevents one
route from hammering a failing model while another route's breaker is
still closed.

<details>
<summary>Visual companion diagram (inline)</summary>

<svg viewBox="0 0 1000 640">
        <defs>
          <marker id="02_circuit_breaker__arrow" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#64748b" />
          </marker>
          <marker id="02_circuit_breaker__arrow-emerald" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#34d399" />
          </marker>
          <marker id="02_circuit_breaker__arrow-amber" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#fbbf24" />
          </marker>
          <marker id="02_circuit_breaker__arrow-rose" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#fb7185" />
          </marker>
          <pattern id="02_circuit_breaker__grid" width="40" height="40" patternUnits="userSpaceOnUse">
            <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#1e293b" stroke-width="0.5"/>
          </pattern>
        </defs>

        <rect width="100%" height="100%" fill="url(#02_circuit_breaker__grid)" />

        <!-- Title -->
        <text x="500" y="40" fill="white" font-size="13" font-weight="700" text-anchor="middle">CircuitBreaker state machine (one instance per model)</text>
        <text x="500" y="58" fill="#94a3b8" font-size="9" text-anchor="middle">error_rate threshold + hallucination flag -> transitions; cooldown timer -> half-open</text>

        <!-- CLOSED state -->
        <rect x="80" y="100" width="220" height="120" rx="10" fill="rgba(6, 78, 59, 0.4)" stroke="#34d399" stroke-width="2"/>
        <text x="190" y="128" fill="white" font-size="13" font-weight="700" text-anchor="middle">CLOSED</text>
        <text x="190" y="148" fill="#34d399" font-size="9" text-anchor="middle">requests flow normally</text>
        <text x="190" y="166" fill="#94a3b8" font-size="8" text-anchor="middle">success_count tracked</text>
        <text x="190" y="180" fill="#94a3b8" font-size="8" text-anchor="middle">failure_count tracked</text>
        <text x="190" y="196" fill="#94a3b8" font-size="8" text-anchor="middle">rolling window</text>
        <text x="190" y="212" fill="#34d399" font-size="8" text-anchor="middle">response.circuit_state = "closed"</text>

        <!-- OPEN state -->
        <rect x="390" y="100" width="220" height="120" rx="10" fill="rgba(136, 19, 55, 0.4)" stroke="#fb7185" stroke-width="2"/>
        <text x="500" y="128" fill="white" font-size="13" font-weight="700" text-anchor="middle">OPEN</text>
        <text x="500" y="148" fill="#fb7185" font-size="9" text-anchor="middle">requests short-circuited</text>
        <text x="500" y="166" fill="#94a3b8" font-size="8" text-anchor="middle">model skipped in chain</text>
        <text x="500" y="180" fill="#94a3b8" font-size="8" text-anchor="middle">cooldown timer running</text>
        <text x="500" y="196" fill="#94a3b8" font-size="8" text-anchor="middle">response.circuit_trip = true</text>
        <text x="500" y="212" fill="#fb7185" font-size="8" text-anchor="middle">fallback advances immediately</text>

        <!-- HALF_OPEN state -->
        <rect x="700" y="100" width="220" height="120" rx="10" fill="rgba(120, 53, 15, 0.3)" stroke="#fbbf24" stroke-width="2"/>
        <text x="810" y="128" fill="white" font-size="13" font-weight="700" text-anchor="middle">HALF_OPEN</text>
        <text x="810" y="148" fill="#fbbf24" font-size="9" text-anchor="middle">probe request allowed</text>
        <text x="810" y="166" fill="#94a3b8" font-size="8" text-anchor="middle">single trial request</text>
        <text x="810" y="180" fill="#94a3b8" font-size="8" text-anchor="middle">success -> CLOSED</text>
        <text x="810" y="196" fill="#94a3b8" font-size="8" text-anchor="middle">failure -> OPEN</text>
        <text x="810" y="212" fill="#fbbf24" font-size="8" text-anchor="middle">cooldown elapsed</text>

        <!-- Transitions -->
        <path d="M 300 160 L 388 160" fill="none" stroke="#fb7185" stroke-width="2" marker-end="url(#02_circuit_breaker__arrow-rose)"/>
        <text x="344" y="152" fill="#fb7185" font-size="8" text-anchor="middle">error_rate > threshold</text>
        <text x="344" y="174" fill="#94a3b8" font-size="7" text-anchor="middle">or hallucination flag</text>

        <path d="M 610 160 L 698 160" fill="none" stroke="#fbbf24" stroke-width="2" marker-end="url(#02_circuit_breaker__arrow-amber)"/>
        <text x="654" y="152" fill="#fbbf24" font-size="8" text-anchor="middle">cooldown elapsed</text>

        <path d="M 810 220 Q 810 260 500 260 Q 190 260 190 220" fill="none" stroke="#34d399" stroke-width="2" marker-end="url(#02_circuit_breaker__arrow-emerald)"/>
        <text x="500" y="252" fill="#34d399" font-size="8" text-anchor="middle">probe success -> reset failure_count</text>

        <path d="M 810 220 Q 810 290 500 290 Q 500 290 500 220" fill="none" stroke="#fb7185" stroke-width="2" stroke-dasharray="5,5" marker-end="url(#02_circuit_breaker__arrow-rose)"/>
        <text x="660" y="282" fill="#fb7185" font-size="8" text-anchor="middle">probe failure -> back to OPEN (cooldown restarts)</text>

        <!-- Per-model registry -->
        <rect x="60" y="340" width="880" height="240" rx="10" fill="rgba(15, 23, 42, 0.5)" stroke="#1e293b" stroke-width="1.5"/>
        <text x="80" y="366" fill="white" font-size="11" font-weight="600">Per-model breaker registry (global, shared across routes)</text>
        <text x="80" y="382" fill="#94a3b8" font-size="8">keyed by model name; each entry holds state + counters + last_trip_at</text>

        <!-- Model rows -->
        <rect x="80" y="400" width="840" height="40" rx="6" fill="rgba(6, 78, 59, 0.4)" stroke="#34d399" stroke-width="1"/>
        <text x="100" y="424" fill="white" font-size="10" font-weight="600">claude-3-5-sonnet</text>
        <text x="320" y="424" fill="#34d399" font-size="9">state: CLOSED</text>
        <text x="500" y="424" fill="#94a3b8" font-size="9">error_rate: 0.02</text>
        <text x="700" y="424" fill="#94a3b8" font-size="9">used by: summarize, code-review</text>

        <rect x="80" y="448" width="840" height="40" rx="6" fill="rgba(136, 19, 55, 0.4)" stroke="#fb7185" stroke-width="1"/>
        <text x="100" y="472" fill="white" font-size="10" font-weight="600">gpt-4o</text>
        <text x="320" y="472" fill="#fb7185" font-size="9">state: OPEN</text>
        <text x="500" y="472" fill="#94a3b8" font-size="9">error_rate: 0.34 (cooldown: 45s left)</text>
        <text x="700" y="472" fill="#94a3b8" font-size="9">used by: summarize, code-review, cheap-chat</text>

        <rect x="80" y="496" width="840" height="40" rx="6" fill="rgba(120, 53, 15, 0.3)" stroke="#fbbf24" stroke-width="1"/>
        <text x="100" y="520" fill="white" font-size="10" font-weight="600">gemini-1.5-pro</text>
        <text x="320" y="520" fill="#fbbf24" font-size="9">state: HALF_OPEN</text>
        <text x="500" y="520" fill="#94a3b8" font-size="9">error_rate: 0.18 (probe in flight)</text>
        <text x="700" y="520" fill="#94a3b8" font-size="9">used by: code-review</text>

        <rect x="80" y="544" width="840" height="40" rx="6" fill="rgba(6, 78, 59, 0.4)" stroke="#34d399" stroke-width="1"/>
        <text x="100" y="568" fill="white" font-size="10" font-weight="600">llama-3.1-70b</text>
        <text x="320" y="568" fill="#34d399" font-size="9">state: CLOSED</text>
        <text x="500" y="568" fill="#94a3b8" font-size="9">error_rate: 0.05</text>
        <text x="700" y="568" fill="#94a3b8" font-size="9">used by: summarize, cheap-chat</text>

        <text x="60" y="610" fill="#94a3b8" font-size="8">Why global: a model that is failing for one route is likely failing for all routes -> skip it everywhere, not just where it broke.</text>
        <text x="60" y="624" fill="#94a3b8" font-size="8">Response surfaces circuit_state and circuit_trip so callers and dashboards can react without scraping logs.</text>
      </svg>

</details>

### Backend as protocol

`Backend` is a `runtime_checkable` Protocol with a single method:
`generate(model, messages, ...) -> BackendResponse`. Any object with
that method is a valid backend. This makes it trivial to add new
providers or wrap existing SDKs.

<details>
<summary>Visual companion diagram (inline)</summary>

<svg viewBox="0 0 1000 620">
        <defs>
          <marker id="05_backends__arrow-cyan" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#22d3ee" />
          </marker>
          <marker id="05_backends__arrow-emerald" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#34d399" />
          </marker>
          <marker id="05_backends__arrow-amber" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#fbbf24" />
          </marker>
          <marker id="05_backends__arrow-violet" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#a78bfa" />
          </marker>
          <marker id="05_backends__arrow-rose" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#fb7185" />
          </marker>
          <pattern id="05_backends__grid" width="40" height="40" patternUnits="userSpaceOnUse">
            <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#1e293b" stroke-width="0.5"/>
          </pattern>
        </defs>

        <rect width="100%" height="100%" fill="url(#05_backends__grid)" />

        <!-- Driver -->
        <rect x="380" y="30" width="240" height="60" rx="10" fill="rgba(120, 53, 15, 0.3)" stroke="#fbbf24" stroke-width="2"/>
        <text x="500" y="56" fill="white" font-size="12" font-weight="700" text-anchor="middle">FacadeDriver</text>
        <text x="500" y="74" fill="#94a3b8" font-size="9" text-anchor="middle">calls backend.generate(req)</text>

        <!-- Backend Protocol -->
        <rect x="320" y="130" width="360" height="120" rx="10" fill="rgba(8, 51, 68, 0.4)" stroke="#22d3ee" stroke-width="2"/>
        <text x="500" y="158" fill="white" font-size="13" font-weight="700" text-anchor="middle">Backend (Protocol)</text>
        <text x="500" y="178" fill="#22d3ee" font-size="9" text-anchor="middle">@runtime_checkable</text>
        <text x="500" y="198" fill="#94a3b8" font-size="9" text-anchor="middle">def generate(self, req: Request) -> Response</text>
        <text x="500" y="214" fill="#94a3b8" font-size="9" text-anchor="middle">def stream(self, req: Request) -> Iterator[Chunk]</text>
        <text x="500" y="230" fill="#94a3b8" font-size="9" text-anchor="middle">def health(self) -> HealthStatus</text>
        <text x="500" y="246" fill="#94a3b8" font-size="9" text-anchor="middle">name: str, capabilities: set[Capability]</text>

        <path d="M 500 90 L 500 128" fill="none" stroke="#22d3ee" stroke-width="2" marker-end="url(#05_backends__arrow-cyan)"/>

        <!-- Implementations -->
        <rect x="40" y="300" width="180" height="140" rx="10" fill="rgba(6, 78, 59, 0.4)" stroke="#34d399" stroke-width="1.5"/>
        <text x="130" y="326" fill="white" font-size="11" font-weight="700" text-anchor="middle">AnthropicBackend</text>
        <text x="130" y="346" fill="#34d399" font-size="8" text-anchor="middle">implements Backend</text>
        <text x="130" y="366" fill="#94a3b8" font-size="8" text-anchor="middle">messages API</text>
        <text x="130" y="382" fill="#94a3b8" font-size="8" text-anchor="middle">system + tools</text>
        <text x="130" y="398" fill="#94a3b8" font-size="8" text-anchor="middle">prompt caching</text>
        <text x="130" y="414" fill="#94a3b8" font-size="8" text-anchor="middle">streaming via SSE</text>
        <text x="130" y="430" fill="#94a3b8" font-size="8" text-anchor="middle">caps: {tools, vision}</text>

        <rect x="240" y="300" width="180" height="140" rx="10" fill="rgba(8, 51, 68, 0.4)" stroke="#22d3ee" stroke-width="1.5"/>
        <text x="330" y="326" fill="white" font-size="11" font-weight="700" text-anchor="middle">OpenAIBackend</text>
        <text x="330" y="346" fill="#22d3ee" font-size="8" text-anchor="middle">implements Backend</text>
        <text x="330" y="366" fill="#94a3b8" font-size="8" text-anchor="middle">chat.completions</text>
        <text x="330" y="382" fill="#94a3b8" font-size="8" text-anchor="middle">function calling</text>
        <text x="330" y="398" fill="#94a3b8" font-size="8" text-anchor="middle">json mode</text>
        <text x="330" y="414" fill="#94a3b8" font-size="8" text-anchor="middle">streaming via SSE</text>
        <text x="330" y="430" fill="#94a3b8" font-size="8" text-anchor="middle">caps: {tools, json}</text>

        <rect x="440" y="300" width="180" height="140" rx="10" fill="rgba(120, 53, 15, 0.3)" stroke="#fbbf24" stroke-width="1.5"/>
        <text x="530" y="326" fill="white" font-size="11" font-weight="700" text-anchor="middle">GeminiBackend</text>
        <text x="530" y="346" fill="#fbbf24" font-size="8" text-anchor="middle">implements Backend</text>
        <text x="530" y="366" fill="#94a3b8" font-size="8" text-anchor="middle">generateContent</text>
        <text x="530" y="382" fill="#94a3b8" font-size="8" text-anchor="middle">function declarations</text>
        <text x="530" y="398" fill="#94a3b8" font-size="8" text-anchor="middle">multimodal inline</text>
        <text x="530" y="414" fill="#94a3b8" font-size="8" text-anchor="middle">streaming via SSE</text>
        <text x="530" y="430" fill="#94a3b8" font-size="8" text-anchor="middle">caps: {tools, vision}</text>

        <rect x="640" y="300" width="180" height="140" rx="10" fill="rgba(76, 29, 149, 0.3)" stroke="#a78bfa" stroke-width="1.5"/>
        <text x="730" y="326" fill="white" font-size="11" font-weight="700" text-anchor="middle">OllamaBackend</text>
        <text x="730" y="346" fill="#a78bfa" font-size="8" text-anchor="middle">implements Backend</text>
        <text x="730" y="366" fill="#94a3b8" font-size="8" text-anchor="middle">/api/chat</text>
        <text x="730" y="382" fill="#94a3b8" font-size="8" text-anchor="middle">local models</text>
        <text x="730" y="398" fill="#94a3b8" font-size="8" text-anchor="middle">no auth, no rate limit</text>
        <text x="730" y="414" fill="#94a3b8" font-size="8" text-anchor="middle">streaming via NDJSON</text>
        <text x="730" y="430" fill="#94a3b8" font-size="8" text-anchor="middle">caps: {local}</text>

        <rect x="840" y="300" width="120" height="140" rx="10" fill="rgba(136, 19, 55, 0.4)" stroke="#fb7185" stroke-width="1.5"/>
        <text x="900" y="326" fill="white" font-size="11" font-weight="700" text-anchor="middle">Custom</text>
        <text x="900" y="346" fill="#fb7185" font-size="8" text-anchor="middle">implements Backend</text>
        <text x="900" y="366" fill="#94a3b8" font-size="8" text-anchor="middle">user-defined</text>
        <text x="900" y="382" fill="#94a3b8" font-size="8" text-anchor="middle">internal API</text>
        <text x="900" y="398" fill="#94a3b8" font-size="8" text-anchor="middle">vLLM, TGI, etc.</text>
        <text x="900" y="414" fill="#94a3b8" font-size="8" text-anchor="middle">drop-in</text>
        <text x="900" y="430" fill="#94a3b8" font-size="8" text-anchor="middle">caps: {...}</text>

        <!-- Arrows from protocol to impls -->
        <path d="M 380 250 Q 200 270 130 298" fill="none" stroke="#34d399" stroke-width="1.5" marker-end="url(#05_backends__arrow-emerald)"/>
        <path d="M 440 250 Q 380 270 330 298" fill="none" stroke="#22d3ee" stroke-width="1.5" marker-end="url(#05_backends__arrow-cyan)"/>
        <path d="M 560 250 Q 560 270 530 298" fill="none" stroke="#fbbf24" stroke-width="1.5" marker-end="url(#05_backends__arrow-amber)"/>
        <path d="M 620 250 Q 700 270 730 298" fill="none" stroke="#a78bfa" stroke-width="1.5" marker-end="url(#05_backends__arrow-violet)"/>
        <path d="M 680 250 Q 820 270 900 298" fill="none" stroke="#fb7185" stroke-width="1.5" marker-end="url(#05_backends__arrow-rose)"/>

        <!-- Request/Response shapes -->
        <rect x="60" y="480" width="440" height="120" rx="10" fill="rgba(15, 23, 42, 0.5)" stroke="#1e293b" stroke-width="1.5"/>
        <text x="80" y="506" fill="white" font-size="11" font-weight="600">Request (provider-agnostic)</text>
        <text x="80" y="524" fill="#94a3b8" font-size="8">messages: list[Message], system: str, tools: list[Tool]</text>
        <text x="80" y="540" fill="#94a3b8" font-size="8">temperature, max_tokens, stop, json_schema</text>
        <text x="80" y="556" fill="#94a3b8" font-size="8">stream: bool, metadata: dict</text>
        <text x="80" y="572" fill="#34d399" font-size="8">-> every backend accepts the same shape</text>
        <text x="80" y="588" fill="#94a3b8" font-size="8">backend translates to its native format internally</text>

        <rect x="520" y="480" width="440" height="120" rx="10" fill="rgba(15, 23, 42, 0.5)" stroke="#1e293b" stroke-width="1.5"/>
        <text x="540" y="506" fill="white" font-size="11" font-weight="600">Response (provider-agnostic)</text>
        <text x="540" y="524" fill="#94a3b8" font-size="8">content: str, tool_calls: list[ToolCall]</text>
        <text x="540" y="540" fill="#94a3b8" font-size="8">finish_reason, usage: {in, out}, latency_ms</text>
        <text x="540" y="556" fill="#94a3b8" font-size="8">model_used, circuit_state, circuit_trip</text>
        <text x="540" y="572" fill="#34d399" font-size="8">-> driver never parses provider JSON</text>
        <text x="540" y="588" fill="#94a3b8" font-size="8">backend normalizes its native response into this shape</text>
      </svg>

</details>

### Telemetry never breaks the request

The driver wraps `sink.emit()` in a try/except. A broken telemetry
sink (e.g. a full disk) must never cause a user-facing failure.

<details>
<summary>Visual companion diagram (inline)</summary>

<svg viewBox="0 0 1000 640">
        <defs>
          <marker id="04_telemetry__arrow-violet" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#a78bfa" />
          </marker>
          <marker id="04_telemetry__arrow-cyan" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#22d3ee" />
          </marker>
          <marker id="04_telemetry__arrow-emerald" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#34d399" />
          </marker>
          <marker id="04_telemetry__arrow-amber" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#fbbf24" />
          </marker>
          <marker id="04_telemetry__arrow-rose" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#fb7185" />
          </marker>
          <pattern id="04_telemetry__grid" width="40" height="40" patternUnits="userSpaceOnUse">
            <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#1e293b" stroke-width="0.5"/>
          </pattern>
        </defs>

        <rect width="100%" height="100%" fill="url(#04_telemetry__grid)" />

        <!-- Driver core -->
        <rect x="380" y="40" width="240" height="80" rx="10" fill="rgba(120, 53, 15, 0.3)" stroke="#fbbf24" stroke-width="2"/>
        <text x="500" y="66" fill="white" font-size="13" font-weight="700" text-anchor="middle">Driver.generate()</text>
        <text x="500" y="84" fill="#94a3b8" font-size="9" text-anchor="middle">single call site</text>
        <text x="500" y="100" fill="#fbbf24" font-size="8" text-anchor="middle">emits one TelemetryEvent</text>

        <!-- TelemetryEvent -->
        <rect x="350" y="160" width="300" height="100" rx="10" fill="rgba(8, 51, 68, 0.4)" stroke="#22d3ee" stroke-width="2"/>
        <text x="500" y="186" fill="white" font-size="12" font-weight="700" text-anchor="middle">TelemetryEvent</text>
        <text x="500" y="204" fill="#94a3b8" font-size="8" text-anchor="middle">route, model_used, latency_ms</text>
        <text x="500" y="218" fill="#94a3b8" font-size="8" text-anchor="middle">attempts, circuit_state, circuit_trip</text>
        <text x="500" y="232" fill="#94a3b8" font-size="8" text-anchor="middle">prompt_hash, tokens_in, tokens_out</text>
        <text x="500" y="246" fill="#94a3b8" font-size="8" text-anchor="middle">hallucination_flag, error_class</text>

        <path d="M 500 120 L 500 158" fill="none" stroke="#22d3ee" stroke-width="2" marker-end="url(#04_telemetry__arrow-cyan)"/>

        <!-- Sink bus -->
        <rect x="100" y="300" width="800" height="60" rx="10" fill="rgba(76, 29, 149, 0.3)" stroke="#a78bfa" stroke-width="2"/>
        <text x="500" y="326" fill="white" font-size="12" font-weight="700" text-anchor="middle">TelemetrySink (fan-out bus)</text>
        <text x="500" y="344" fill="#a78bfa" font-size="8" text-anchor="middle">each sink implements .emit(event) -> None; failures are isolated</text>

        <path d="M 500 260 L 500 298" fill="none" stroke="#a78bfa" stroke-width="2" marker-end="url(#04_telemetry__arrow-violet)"/>

        <!-- Sinks -->
        <rect x="40" y="400" width="180" height="120" rx="10" fill="rgba(6, 78, 59, 0.4)" stroke="#34d399" stroke-width="1.5"/>
        <text x="130" y="426" fill="white" font-size="11" font-weight="700" text-anchor="middle">ConsoleSink</text>
        <text x="130" y="446" fill="#34d399" font-size="8" text-anchor="middle">stdout (dev)</text>
        <text x="130" y="464" fill="#94a3b8" font-size="8" text-anchor="middle">pretty JSON</text>
        <text x="130" y="480" fill="#94a3b8" font-size="8" text-anchor="middle">level: INFO</text>
        <text x="130" y="498" fill="#94a3b8" font-size="8" text-anchor="middle">zero deps</text>

        <rect x="240" y="400" width="180" height="120" rx="10" fill="rgba(8, 51, 68, 0.4)" stroke="#22d3ee" stroke-width="1.5"/>
        <text x="330" y="426" fill="white" font-size="11" font-weight="700" text-anchor="middle">OTelSink</text>
        <text x="330" y="446" fill="#22d3ee" font-size="8" text-anchor="middle">OpenTelemetry</text>
        <text x="330" y="464" fill="#94a3b8" font-size="8" text-anchor="middle">span per attempt</text>
        <text x="330" y="480" fill="#94a3b8" font-size="8" text-anchor="middle">attributes = event</text>
        <text x="330" y="498" fill="#94a3b8" font-size="8" text-anchor="middle">trace context</text>

        <rect x="440" y="400" width="180" height="120" rx="10" fill="rgba(120, 53, 15, 0.3)" stroke="#fbbf24" stroke-width="1.5"/>
        <text x="530" y="426" fill="white" font-size="11" font-weight="700" text-anchor="middle">LangfuseSink</text>
        <text x="530" y="446" fill="#fbbf24" font-size="8" text-anchor="middle">Langfuse</text>
        <text x="530" y="464" fill="#94a3b8" font-size="8" text-anchor="middle">generation + span</text>
        <text x="530" y="480" fill="#94a3b8" font-size="8" text-anchor="middle">prompt + completion</text>
        <text x="530" y="498" fill="#94a3b8" font-size="8" text-anchor="middle">user_id, session_id</text>

        <rect x="640" y="400" width="180" height="120" rx="10" fill="rgba(136, 19, 55, 0.4)" stroke="#fb7185" stroke-width="1.5"/>
        <text x="730" y="426" fill="white" font-size="11" font-weight="700" text-anchor="middle">FileSink</text>
        <text x="730" y="446" fill="#fb7185" font-size="8" text-anchor="middle">JSONL file</text>
        <text x="730" y="464" fill="#94a3b8" font-size="8" text-anchor="middle">rotated daily</text>
        <text x="730" y="480" fill="#94a3b8" font-size="8" text-anchor="middle">gzipped archive</text>
        <text x="730" y="498" fill="#94a3b8" font-size="8" text-anchor="middle">local audit trail</text>

        <rect x="840" y="400" width="120" height="120" rx="10" fill="rgba(76, 29, 149, 0.3)" stroke="#a78bfa" stroke-width="1.5"/>
        <text x="900" y="426" fill="white" font-size="11" font-weight="700" text-anchor="middle">Custom</text>
        <text x="900" y="446" fill="#a78bfa" font-size="8" text-anchor="middle">plugin sink</text>
        <text x="900" y="464" fill="#94a3b8" font-size="8" text-anchor="middle">user-defined</text>
        <text x="900" y="480" fill="#94a3b8" font-size="8" text-anchor="middle">implements</text>
        <text x="900" y="498" fill="#94a3b8" font-size="8" text-anchor="middle">.emit(event)</text>

        <!-- Fan-out arrows -->
        <path d="M 200 360 Q 200 380 130 398" fill="none" stroke="#34d399" stroke-width="1.5" marker-end="url(#04_telemetry__arrow-emerald)"/>
        <path d="M 350 360 Q 350 380 330 398" fill="none" stroke="#22d3ee" stroke-width="1.5" marker-end="url(#04_telemetry__arrow-cyan)"/>
        <path d="M 500 360 L 530 398" fill="none" stroke="#fbbf24" stroke-width="1.5" marker-end="url(#04_telemetry__arrow-amber)"/>
        <path d="M 650 360 Q 650 380 730 398" fill="none" stroke="#fb7185" stroke-width="1.5" marker-end="url(#04_telemetry__arrow-rose)"/>
        <path d="M 800 360 Q 800 380 900 398" fill="none" stroke="#a78bfa" stroke-width="1.5" marker-end="url(#04_telemetry__arrow-violet)"/>

        <text x="60" y="560" fill="#94a3b8" font-size="8">Why fan-out: one source of truth in the driver, many destinations for ops, ML, and audit; adding a sink never touches the call site.</text>
        <text x="60" y="574" fill="#94a3b8" font-size="8">Sink failures are caught and logged; a broken Langfuse export must not break the user's generation request.</text>
        <text x="60" y="588" fill="#94a3b8" font-size="8">Sinks are registered at driver construction; tests inject a RecordingSink to assert on the exact event payload.</text>
        <text x="60" y="602" fill="#94a3b8" font-size="8">PII scrubbing happens in the bus before fan-out, so sinks receive a redacted event by default.</text>
      </svg>

</details>

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
