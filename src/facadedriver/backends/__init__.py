"""Backend protocol and implementations.

A Backend is anything that can take a model name + messages and return
a BackendResponse. The driver talks to backends through the Backend
protocol, so new providers can be added without touching the core.
"""

from __future__ import annotations

import time
from typing import Any, Protocol, runtime_checkable

from facadedriver.types import BackendResponse, Message


@runtime_checkable
class Backend(Protocol):
    """Provider-agnostic backend interface."""

    def generate(
        self,
        model: str,
        messages: list[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> BackendResponse:
        """Generate a completion for the given model and messages."""
        ...


class MockBackend:
    """Deterministic in-memory backend for tests and demos.

    Returns a canned response that echoes the last user message and
    reports fake token counts and latency. Never makes a network call.
    """

    def __init__(
        self,
        *,
        content: str | None = None,
        latency_ms: float = 50.0,
        fail_models: set[str] | None = None,
        provider: str = "mock",
    ) -> None:
        self._content = content
        self._latency_ms = latency_ms
        self._fail_models = fail_models or set()
        self._provider = provider
        self.calls: list[dict[str, Any]] = []

    def generate(
        self,
        model: str,
        messages: list[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> BackendResponse:
        self.calls.append(
            {"model": model, "messages": messages, "kwargs": kwargs}
        )
        if model in self._fail_models:
            raise RuntimeError(f"MockBackend forced failure for model '{model}'")
        start = time.perf_counter()
        last_user = next(
            (m["content"] for m in reversed(messages) if m.get("role") == "user"),
            "",
        )
        content = self._content if self._content is not None else f"[mock:{model}] {last_user}"
        elapsed = (time.perf_counter() - start) * 1000
        return BackendResponse(
            content=content,
            model=model,
            provider=self._provider,
            input_tokens=sum(len(m.get("content", "").split()) for m in messages),
            output_tokens=len(content.split()),
            cost_usd=0.0,
            latency_ms=max(elapsed, self._latency_ms),
            raw={"mock": True},
        )


class RawSDKBackend:
    """Backend that calls provider SDKs directly (openai, anthropic, google-genai).

    Routes based on the model name prefix:
        gpt-* / openai/*  -> openai
        claude-*          -> anthropic
        gemini-*          -> google.genai

    The corresponding SDK must be installed. If it isn't, a clear
    ImportError is raised at call time (not import time) so the rest of
    FacadeDriver stays usable without all three SDKs.
    """

    def __init__(self, providers: dict[str, Any] | None = None) -> None:
        # providers maps provider name -> configured client (optional).
        # If absent, the SDK is constructed lazily from env vars.
        self._providers = providers or {}

    def _provider_for(self, model: str) -> str:
        if model.startswith("gpt-") or model.startswith("openai/"):
            return "openai"
        if model.startswith("claude-"):
            return "anthropic"
        if model.startswith("gemini-"):
            return "google"
        raise ValueError(f"Unknown provider for model '{model}'")

    def generate(
        self,
        model: str,
        messages: list[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> BackendResponse:
        provider = self._provider_for(model)
        start = time.perf_counter()
        if provider == "openai":
            resp = self._call_openai(model, messages, temperature, max_tokens, kwargs)
        elif provider == "anthropic":
            resp = self._call_anthropic(model, messages, temperature, max_tokens, kwargs)
        else:
            resp = self._call_google(model, messages, temperature, max_tokens, kwargs)
        latency = (time.perf_counter() - start) * 1000
        resp.provider = provider
        resp.latency_ms = latency
        return resp

    def _call_openai(
        self,
        model: str,
        messages: list[Message],
        temperature: float,
        max_tokens: int | None,
        kwargs: dict[str, Any],
    ) -> BackendResponse:
        try:
            from openai import OpenAI  # type: ignore
        except ImportError as e:
            raise ImportError(
                "openai SDK not installed. Run `pip install openai` to use gpt-* models."
            ) from e
        client = self._providers.get("openai") or OpenAI()
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
        choice = resp.choices[0]
        usage = resp.usage
        return BackendResponse(
            content=choice.message.content or "",
            model=model,
            provider="openai",
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            raw=resp.model_dump() if hasattr(resp, "model_dump") else None,
        )

    def _call_anthropic(
        self,
        model: str,
        messages: list[Message],
        temperature: float,
        max_tokens: int | None,
        kwargs: dict[str, Any],
    ) -> BackendResponse:
        try:
            import anthropic  # type: ignore
        except ImportError as e:
            raise ImportError(
                "anthropic SDK not installed. Run `pip install anthropic` to use claude-* models."
            ) from e
        client = self._providers.get("anthropic") or anthropic.Anthropic()
        system = next((m["content"] for m in messages if m.get("role") == "system"), None)
        user_messages = [m for m in messages if m.get("role") != "system"]
        resp = client.messages.create(
            model=model,
            messages=user_messages,
            system=system or anthropic.NOT_GIVEN,
            temperature=temperature,
            max_tokens=max_tokens or 1024,
            **kwargs,
        )
        content = "".join(block.text for block in resp.content if hasattr(block, "text"))
        return BackendResponse(
            content=content,
            model=model,
            provider="anthropic",
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            raw=resp.model_dump() if hasattr(resp, "model_dump") else None,
        )

    def _call_google(
        self,
        model: str,
        messages: list[Message],
        temperature: float,
        max_tokens: int | None,
        kwargs: dict[str, Any],
    ) -> BackendResponse:
        try:
            from google import genai  # type: ignore
        except ImportError as e:
            raise ImportError(
                "google-genai SDK not installed. Run `pip install google-genai` to use gemini-* models."
            ) from e
        client = self._providers.get("google") or genai.Client()
        # Convert messages to the genai format
        contents = [
            genai.types.Content(role=m["role"], parts=[genai.types.Part(text=m["content"])])
            for m in messages
        ]
        config = genai.types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        )
        resp = client.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )
        text = resp.text or ""
        usage = resp.usage_metadata
        return BackendResponse(
            content=text,
            model=model,
            provider="google",
            input_tokens=usage.prompt_token_count if usage else 0,
            output_tokens=usage.candidates_token_count if usage else 0,
            raw=None,
        )
