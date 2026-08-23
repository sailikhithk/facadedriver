"""FacadeDriver live demo - AI Tinkerers Houston.

This is the exact script for the talk. It tells the FacadeDriver story
in four acts, using only the MockBackend so it runs with zero setup:

  Act 1: The problem - you shipped on one model, now you're stuck.
  Act 2: The fix - route names, not model names. Swap at runtime.
  Act 3: When models fail - fallback chains, graceful degradation.
  Act 4: When models misbehave - circuit breaker, automatic protection.

Run: python3 demo.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from facadedriver import Config, FacadeDriver, MockBackend
from facadedriver.resilience import CircuitBreaker
from facadedriver.telemetry import NullSink
from facadedriver.types import AllProvidersFailedError


def banner(title: str) -> None:
    print()
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)


def pause(msg: str = "") -> None:
    if msg:
        print(f"  >> {msg}")
    time.sleep(0.4)


def act_1_the_problem() -> None:
    banner("Act 1: The Problem")
    print("""
  Your app calls openai.chat.completions.create() in 47 places.
  GPT-4o goes down for 3 hours. Your product is down for 3 hours.

  Or: a new model drops (Claude 3.5, Gemini 1.5). You want to try it.
  You grep for 'gpt-4o' across the codebase. 47 files. Each with its
  own retry logic, its own error handling, its own cost tracking.

  This is the problem FacadeDriver solves.
    """)
    pause("enter FacadeDriver")


def act_2_runtime_swap() -> None:
    banner("Act 2: Route Names, Not Model Names")
    cfg = Config.from_dict({
        "routes": {
            "summarize": {
                "primary": "gpt-4o-mini",
                "fallback": ["claude-3-5-sonnet"],
            }
        }
    })
    driver = FacadeDriver(cfg, backend=MockBackend(), telemetry_sink=NullSink())

    print("  Application code calls: driver.generate('summarize', messages)")
    print(f"  Route 'summarize' -> chain: {driver.router.chain('summarize')}")
    pause()

    r1 = driver.generate("summarize", [{"role": "user", "content": "summarize this"}])
    print(f"  Request 1 served by: {r1.model}")
    pause("Claude 3.5 Sonnet just launched. Let's try it. No redeploy.")

    driver.swap("summarize", "claude-3-5-sonnet")
    print(f"  After swap -> chain: {driver.router.chain('summarize')}")
    r2 = driver.generate("summarize", [{"role": "user", "content": "summarize this"}])
    print(f"  Request 2 served by: {r2.model}")
    pause("GPT-4o-mini is back in stock. Swap back.")

    driver.swap("summarize", "gpt-4o-mini")
    r3 = driver.generate("summarize", [{"role": "user", "content": "summarize this"}])
    print(f"  Request 3 served by: {r3.model}")
    print()
    print("  Zero code changes. Zero redeploy. Zero downtime.")


def act_3_fallback() -> None:
    banner("Act 3: Fallback Chains")
    cfg = Config.from_dict({
        "routes": {
            "summarize": {
                "primary": "gpt-4o-mini",
                "fallback": ["claude-3-5-sonnet", "gemini-1.5-flash"],
                "retry": {"count": 0, "backoff": "fixed", "base_ms": 1},
            }
        }
    })
    driver = FacadeDriver(cfg, backend=MockBackend(), telemetry_sink=NullSink())

    print(f"  Chain: {driver.router.chain('summarize')}")
    pause("GPT-4o-mini has an outage. Watch the fallback.")

    driver_failing = FacadeDriver(
        cfg,
        backend=MockBackend(fail_models={"gpt-4o-mini"}),
        telemetry_sink=NullSink(),
    )
    r = driver_failing.generate(
        "summarize", [{"role": "user", "content": "degrade gracefully"}]
    )
    print(f"  Served by: {r.model}")
    print(f"  fallback_used: {r.fallback_used}")
    print(f"  chain tried: {' -> '.join(r.fallback_chain)}")
    print()
    print("  The user never saw an error. The SRE got a telemetry event.")
    pause("now what if ALL models fail?")


def act_4_circuit_breaker() -> None:
    banner("Act 4: Circuit Breaker")
    cfg = Config.from_dict({
        "routes": {
            "summarize": {
                "primary": "gpt-4o-mini",
                "fallback": ["claude-3-5-sonnet"],
                "retry": {"count": 0, "backoff": "fixed", "base_ms": 1},
            }
        }
    })
    breaker = CircuitBreaker(error_rate_threshold=0.5, min_requests=4, cooldown_s=60)
    driver = FacadeDriver(
        cfg,
        backend=MockBackend(fail_models={"gpt-4o-mini"}),
        telemetry_sink=NullSink(),
        circuit_breaker=breaker,
    )

    print("  gpt-4o-mini is returning 500s. Let's hammer it.")
    for i in range(4):
        try:
            driver.generate("summarize", [{"role": "user", "content": f"req {i}"}])
        except AllProvidersFailedError:
            pass

    h = driver.health("gpt-4o-mini")
    print(f"  After 4 failures:")
    print(f"    circuit_state: {h.circuit_state.value}")
    print(f"    error_rate:    {h.error_rate:.0%} ({h.error_count}/{h.request_count})")
    print(f"    healthy:       {h.healthy}")
    pause("breaker is OPEN. Next request skips gpt-4o-mini entirely.")

    r = driver.generate("summarize", [{"role": "user", "content": "post-trip"}])
    print(f"  Served by: {r.model} (gpt-4o-mini was skipped)")
    print(f"  circuit_breaker_trip: {r.circuit_breaker_trip}")
    print()
    print("  The breaker protects the user experience AND your wallet")
    print("  (no more paying for requests that are going to fail).")


def closing() -> None:
    banner("FacadeDriver")
    print("""
  Model-agnostic orchestration for multi-LLM production systems.

  - Route names, not model names
  - Runtime swap with zero downtime
  - Fallback chains with graceful degradation
  - Circuit breaker for automatic failure protection
  - Per-request cost/latency telemetry
  - Async support, CLI, FastAPI server, Prometheus exporter
  - Plugin system for custom backends and telemetry sinks

  github.com/sailikhithk/facadedriver
    """)


def main() -> None:
    act_1_the_problem()
    act_2_runtime_swap()
    act_3_fallback()
    act_4_circuit_breaker()
    closing()


if __name__ == "__main__":
    main()
