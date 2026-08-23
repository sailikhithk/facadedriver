"""LiteLLM backend - pluggable alternative to RawSDKBackend.

Uses the litellm library (https://github.com/BerriAI/litellm) which
unifies 100+ LLM providers behind a single `completion()` call.

Install with: `pip install litellm`
"""

from __future__ import annotations

import time
from typing import Any

from facadedriver.types import BackendResponse, Message


class LiteLLMBackend:
    """Backend that delegates to litellm.completion().

    LiteLLM handles provider routing, retries, and cost calculation
    internally. This backend is a thin adapter that converts to
    FacadeDriver's BackendResponse.
    """

    def __init__(self, **default_kwargs: Any) -> None:
        self._default_kwargs = default_kwargs

    def generate(
        self,
        model: str,
        messages: list[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> BackendResponse:
        try:
            import litellm  # type: ignore
        except ImportError as e:
            raise ImportError(
                "litellm not installed. Run `pip install litellm` to use the litellm backend."
            ) from e
        merged = {**self._default_kwargs, **kwargs}
        start = time.perf_counter()
        resp = litellm.completion(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **merged,
        )
        latency = (time.perf_counter() - start) * 1000
        choice = resp.choices[0]
        usage = resp.usage
        cost = litellm.completion_cost(
            model=model,
            prompt=" ".join(m.get("content", "") for m in messages),
            completion=choice.message.content or "",
        )
        return BackendResponse(
            content=choice.message.content or "",
            model=model,
            provider="litellm",
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            cost_usd=float(cost) if cost else None,
            latency_ms=latency,
            raw=resp.model_dump() if hasattr(resp, "model_dump") else None,
        )
