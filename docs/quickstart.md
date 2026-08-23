# Quickstart

## 1. Install

```bash
pip install facadedriver
pip install "facadedriver[openai,anthropic,google]"  # provider SDKs
```

## 2. Configure

Create `facadedriver.yaml`:

```yaml
routes:
  summarize:
    primary: gpt-4o-mini
    fallback:
      - claude-3-5-sonnet
      - gemini-1.5-flash
    retry:
      count: 2
      backoff: exponential
      base_ms: 200
    circuit_breaker:
      error_rate_threshold: 0.15
      min_requests: 20
      cooldown_s: 60

providers:
  openai:
    api_key: ${OPENAI_API_KEY}
  anthropic:
    api_key: ${ANTHROPIC_API_KEY}
  google:
    api_key: ${GOOGLE_API_KEY}

backend:
  type: raw_sdk

telemetry:
  sinks: [structlog]
```

## 3. Use

```python
from facadedriver import Config, FacadeDriver, RawSDKBackend

cfg = Config.from_yaml("facadedriver.yaml")
driver = FacadeDriver(cfg, backend=RawSDKBackend())

resp = driver.generate("summarize", [
    {"role": "user", "content": "Summarize this article..."},
])
print(resp.content)
print(f"served by {resp.model} in {resp.latency_ms:.0f}ms")
```

## 4. Swap at runtime

```python
# Claude 3.5 Sonnet just launched. Try it without redeploying.
driver.swap("summarize", "claude-3-5-sonnet")
```

## 5. Observe

Every `generate()` call emits a structured telemetry event:

```json
{"ts": 1724313600.0, "route": "summarize", "model": "gpt-4o-mini",
 "cost_usd": 0.0001, "latency_ms": 340, "fallback_used": false}
```

## Mock backend (no API keys needed)

For tests and demos:

```python
from facadedriver import MockBackend
driver = FacadeDriver(cfg, backend=MockBackend())
```
