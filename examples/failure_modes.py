"""Failure-mode demo: fallback chains and circuit breaker in action.

Shows three scenarios:
  1. Primary fails -> fallback succeeds (graceful degradation)
  2. All models fail -> AllProvidersFailedError
  3. Circuit breaker opens after enough failures, blocks calls

Uses MockBackend with fail_models to simulate provider outages.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from facadedriver import Config, FacadeDriver, MockBackend
from facadedriver.telemetry import NullSink
from facadedriver.types import AllProvidersFailedError
from facadedriver.resilience import CircuitBreaker


def make_driver(fail: set[str], breaker: CircuitBreaker | None = None) -> FacadeDriver:
    cfg = Config.from_dict({
        "routes": {
            "summarize": {
                "primary": "gpt-4o-mini",
                "fallback": ["claude-3-5-sonnet", "gemini-1.5-flash"],
                "retry": {"count": 0, "backoff": "fixed", "base_ms": 1},
                "circuit_breaker": {
                    "error_rate_threshold": 0.5,
                    "min_requests": 4,
                    "cooldown_s": 60,
                },
            }
        }
    })
    return FacadeDriver(
        cfg,
        backend=MockBackend(fail_models=fail),
        telemetry_sink=NullSink(),
        circuit_breaker=breaker,
    )


def scenario_1() -> None:
    print("=== Scenario 1: primary fails, fallback succeeds ===")
    d = make_driver({"gpt-4o-mini"})
    r = d.generate("summarize", [{"role": "user", "content": "degrade gracefully"}])
    print(f"  served by: {r.model}")
    print(f"  fallback_used: {r.fallback_used}")
    print(f"  chain tried: {r.fallback_chain}")


def scenario_2() -> None:
    print("\n=== Scenario 2: all models fail ===")
    d = make_driver({"gpt-4o-mini", "claude-3-5-sonnet", "gemini-1.5-flash"})
    try:
        d.generate("summarize", [{"role": "user", "content": "nothing works"}])
    except AllProvidersFailedError as e:
        print(f"  raised AllProvidersFailedError")
        print(f"  chain tried: {e.chain}")
        print(f"  errors: {len(e.errors)}")


def scenario_3() -> None:
    print("\n=== Scenario 3: circuit breaker opens ===")
    breaker = CircuitBreaker(error_rate_threshold=0.5, min_requests=4, cooldown_s=60)
    d = make_driver({"gpt-4o-mini"}, breaker=breaker)
    # Force 4 failures to trip the breaker (min_requests=4, threshold=0.5)
    for i in range(4):
        try:
            d.generate("summarize", [{"role": "user", "content": f"fail {i}"}])
        except AllProvidersFailedError:
            pass
    h = d.health("gpt-4o-mini")
    print(f"  gpt-4o-mini circuit_state: {h.circuit_state.value}")
    print(f"  gpt-4o-mini error_rate: {h.error_rate:.2f} ({h.error_count}/{h.request_count})")
    print(f"  healthy: {h.healthy}")
    print("  -> next call to gpt-4o-mini will be blocked by the breaker")


def main() -> None:
    scenario_1()
    scenario_2()
    scenario_3()


if __name__ == "__main__":
    main()
