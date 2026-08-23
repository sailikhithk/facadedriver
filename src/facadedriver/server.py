"""FastAPI server mode for FacadeDriver.

Endpoints:
    POST /generate    - {route, messages, temperature?, max_tokens?} -> Response
    GET  /routes      - list routes and their chains
    GET  /health/{model} - circuit breaker health for a model
    POST /swap        - {route, model} -> swap a route's primary at runtime
    GET  /healthz     - liveness probe

Run with: facadedriver serve --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

from typing import Any

from facadedriver.driver import FacadeDriver


def build_app(driver: FacadeDriver):
    """Build a FastAPI app around a FacadeDriver instance."""
    try:
        from fastapi import FastAPI, HTTPException
        from pydantic import BaseModel
    except ImportError as e:
        raise ImportError(
            "FastAPI not installed. Run `pip install fastapi uvicorn` to use server mode."
        ) from e

    app = FastAPI(title="FacadeDriver", version="0.1.0")

    class GenerateRequest(BaseModel):
        route: str
        messages: list[dict[str, Any]]
        temperature: float = 0.0
        max_tokens: int | None = None

    class SwapRequest(BaseModel):
        route: str
        model: str

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/routes")
    def routes() -> dict[str, list[str]]:
        return {r: driver.router.chain(r) for r in driver.routes()}

    @app.get("/health/{model}")
    def health(model: str) -> dict[str, Any]:
        h = driver.health(model)
        return {
            "model": h.model,
            "circuit_state": h.circuit_state.value,
            "error_rate": h.error_rate,
            "requests": h.request_count,
            "errors": h.error_count,
            "last_error": h.last_error,
            "healthy": h.healthy,
        }

    @app.post("/swap")
    def swap(req: SwapRequest) -> dict[str, Any]:
        if not driver.router.has(req.route):
            raise HTTPException(status_code=404, detail=f"route '{req.route}' not found")
        driver.swap(req.route, req.model)
        return {"route": req.route, "new_chain": driver.router.chain(req.route)}

    @app.post("/generate")
    def generate(req: GenerateRequest) -> dict[str, Any]:
        if not driver.router.has(req.route):
            raise HTTPException(status_code=404, detail=f"route '{req.route}' not found")
        try:
            resp = driver.generate(
                req.route, req.messages,
                temperature=req.temperature, max_tokens=req.max_tokens,
            )
        except Exception as e:
            raise HTTPException(status_code=502, detail=str(e))
        return {
            "content": resp.content,
            "model": resp.model,
            "provider": resp.provider,
            "route": resp.route,
            "cost_usd": resp.cost_usd,
            "latency_ms": resp.latency_ms,
            "input_tokens": resp.input_tokens,
            "output_tokens": resp.output_tokens,
            "fallback_used": resp.fallback_used,
            "fallback_chain": resp.fallback_chain,
            "circuit_breaker_trip": resp.circuit_breaker_trip,
            "request_id": resp.request_id,
        }

    return app


def run_app(app: Any, *, host: str = "0.0.0.0", port: int = 8000) -> None:
    import uvicorn

    uvicorn.run(app, host=host, port=port)
