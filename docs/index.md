# FacadeDriver

Model-agnostic orchestration for multi-LLM production systems.

FacadeDriver sits between your application and your LLM providers
(OpenAI, Anthropic, Google, etc.) and gives you:

- **Route names, not model names** - call `generate("summarize", ...)`,
  not `openai.chat.completions.create(model="gpt-4o-mini", ...)`.
- **Runtime swap** - change the model backing a route without
  redeploying or restarting.
- **Fallback chains** - if the primary model fails, automatically fall
  back to the next model in the chain.
- **Circuit breaker** - stop sending traffic to a failing model and
  let it recover.
- **Per-request telemetry** - structured logs of cost, latency, tokens,
  and fallback events.
- **Async support** - `asyncio`-native path for high-throughput services.
- **CLI, FastAPI server, Prometheus exporter** - operational tooling
  out of the box.
- **Plugin system** - custom backends, routers, and telemetry sinks.

## Install

```bash
pip install facadedriver
# with provider SDKs:
pip install "facadedriver[openai,anthropic,google]"
# or everything:
pip install "facadedriver[all]"
```

## 30-second quickstart

```python
from facadedriver import Config, FacadeDriver, MockBackend

cfg = Config.from_dict({
    "routes": {
        "summarize": {
            "primary": "gpt-4o-mini",
            "fallback": ["claude-3-5-sonnet", "gemini-1.5-flash"],
        }
    }
})
driver = FacadeDriver(cfg, backend=MockBackend())
resp = driver.generate("summarize", [{"role": "user", "content": "hello"}])
print(resp.content)
```

## Why?

If your app calls `openai.chat.completions.create()` in 47 places,
you have three problems:

1. **Vendor lock-in**: switching to Anthropic means editing 47 files.
2. **No fallback**: when GPT-4o is down, your product is down.
3. **No observability**: cost and latency are invisible.

FacadeDriver fixes all three by introducing a route layer. Your app
calls `generate("summarize", messages)`. The route maps to a primary
model and a fallback chain. You can swap models at runtime, fall back
automatically on failure, and emit structured telemetry for every
request.

## License

MIT.
