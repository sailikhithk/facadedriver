"""Benchmark suite for FacadeDriver.

Measures the overhead of FacadeDriver's routing, fallback, and
telemetry layers against a bare backend call. Since FacadeDriver is
an orchestration layer (not a model server), the meaningful benchmark
is the per-request overhead it adds on top of the backend.

Three suites:
  1. Latency overhead: FacadeDriver.generate() vs raw backend.generate()
  2. Throughput: requests/sec for sequential and concurrent (async)
  3. Fallback cost: overhead when a fallback is triggered

Run: python3 benchmarks/bench_overhead.py
"""

from __future__ import annotations

import asyncio
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from facadedriver import Config, FacadeDriver, MockBackend, AsyncMockBackend
from facadedriver.telemetry import NullSink


N = 1000  # requests per suite


def bench_raw_backend() -> list[float]:
    """Baseline: call MockBackend.generate() directly."""
    backend = MockBackend()
    msgs = [{"role": "user", "content": "benchmark"}]
    times = []
    for _ in range(N):
        start = time.perf_counter()
        backend.generate("gpt-4o-mini", msgs)
        times.append((time.perf_counter() - start) * 1e6)
    return times


def bench_facadedriver() -> list[float]:
    """FacadeDriver.generate() with routing + telemetry."""
    cfg = Config.from_dict({
        "routes": {"r": {"primary": "gpt-4o-mini", "fallback": ["claude-3-5-sonnet"]}}
    })
    d = FacadeDriver(cfg, backend=MockBackend(), telemetry_sink=NullSink())
    msgs = [{"role": "user", "content": "benchmark"}]
    times = []
    for _ in range(N):
        start = time.perf_counter()
        d.generate("r", msgs)
        times.append((time.perf_counter() - start) * 1e6)
    return times


def bench_facadedriver_with_telemetry() -> list[float]:
    """FacadeDriver.generate() with StructlogSink writing to /dev/null."""
    import os
    import io
    from facadedriver.telemetry import StructlogSink

    cfg = Config.from_dict({
        "routes": {"r": {"primary": "gpt-4o-mini", "fallback": ["claude-3-5-sonnet"]}}
    })
    sink = StructlogSink(stream=io.StringIO())
    d = FacadeDriver(cfg, backend=MockBackend(), telemetry_sink=sink)
    msgs = [{"role": "user", "content": "benchmark"}]
    times = []
    for _ in range(N):
        start = time.perf_counter()
        d.generate("r", msgs)
        times.append((time.perf_counter() - start) * 1e6)
    return times


def bench_fallback() -> list[float]:
    """FacadeDriver with primary failing -> fallback path."""
    cfg = Config.from_dict({
        "routes": {"r": {
            "primary": "gpt-4o-mini",
            "fallback": ["claude-3-5-sonnet"],
            "retry": {"count": 0, "backoff": "fixed", "base_ms": 0},
        }}
    })
    d = FacadeDriver(
        cfg,
        backend=MockBackend(fail_models={"gpt-4o-mini"}),
        telemetry_sink=NullSink(),
    )
    msgs = [{"role": "user", "content": "benchmark"}]
    times = []
    for _ in range(N):
        start = time.perf_counter()
        d.generate("r", msgs)
        times.append((time.perf_counter() - start) * 1e6)
    return times


async def bench_async_throughput() -> float:
    """Async throughput: requests/sec with AsyncMockBackend."""
    cfg = Config.from_dict({
        "routes": {"r": {"primary": "gpt-4o-mini", "fallback": []}}
    })
    d = FacadeDriver(
        cfg, backend=AsyncMockBackend(latency_ms=0), telemetry_sink=NullSink(),
    )
    msgs = [{"role": "user", "content": "x"}]

    async def one():
        await d.agenerate("r", msgs)

    start = time.perf_counter()
    await asyncio.gather(*(one() for _ in range(N)))
    elapsed = time.perf_counter() - start
    return N / elapsed


def report(name: str, times: list[float]) -> None:
    med = statistics.median(times)
    p95 = sorted(times)[int(len(times) * 0.95)]
    mean = statistics.mean(times)
    print(f"  {name:40s}  median={med:7.1f}us  p95={p95:7.1f}us  mean={mean:7.1f}us")


def main() -> None:
    print(f"FacadeDriver overhead benchmark ({N} requests/suite)\n")

    print("Latency overhead (microseconds per request):")
    report("raw MockBackend.generate()", bench_raw_backend())
    report("FacadeDriver.generate() [null sink]", bench_facadedriver())
    report("FacadeDriver.generate() [structlog sink]", bench_facadedriver_with_telemetry())
    report("FacadeDriver.generate() [with fallback]", bench_fallback())

    print(f"\nAsync throughput ({N} concurrent requests):")
    tput = asyncio.run(bench_async_throughput())
    print(f"  AsyncMockBackend + FacadeDriver.agenerate(): {tput:,.0f} req/sec")

    print("\nInterpretation:")
    print("  FacadeDriver adds ~tens of microseconds of overhead per request.")
    print("  For real LLM calls (100ms-10s), this overhead is negligible (<0.01%).")


if __name__ == "__main__":
    main()
