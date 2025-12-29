"""
vLLM provider stub.

This provider is not yet implemented. When implemented, it will provide
access to models running on vLLM inference servers.
"""

from __future__ import annotations

import typing as _typing

import brynhild.api.base as base
import brynhild.api.types as types
import brynhild.constants as _constants


class VLLMProvider(base.LLMProvider):
    """
    vLLM provider (NOT IMPLEMENTED).

    vLLM provides high-performance model inference with an OpenAI-compatible API.
    Common in enterprise deployments for self-hosted inference.
    """

    PROVIDER_TYPE = "vllm"

    def __init__(self, **kwargs: _typing.Any) -> None:
        raise NotImplementedError(
            "vLLM provider is not yet implemented.\n\n"
            "vLLM uses an OpenAI-compatible API similar to Ollama.\n"
            "As a workaround, you may be able to use the Ollama provider\n"
            "with a custom base_url pointing to your vLLM server.\n\n"
            "Contribute an implementation at:\n"
            "  https://github.com/your-repo/brynhild"
        )

    @property
    def name(self) -> str:
        return "vllm"

    @property
    def model(self) -> str:
        return ""

    def supports_tools(self) -> bool:
        return True

    async def complete(
        self,
        messages: list[dict[str, _typing.Any]],
        *,
        system: str | None = None,
        tools: list[types.Tool] | None = None,
        max_tokens: int = _constants.DEFAULT_MAX_TOKENS,
        use_profile: bool = True,
    ) -> types.CompletionResponse:
        raise NotImplementedError("vLLM provider not implemented")

    async def stream(  # noqa: ARG002
        self,
        messages: list[dict[str, _typing.Any]],
        *,
        system: str | None = None,
        tools: list[types.Tool] | None = None,
        max_tokens: int = _constants.DEFAULT_MAX_TOKENS,
        use_profile: bool = True,
    ) -> _typing.AsyncIterator[types.StreamEvent]:
        raise NotImplementedError("vLLM provider not implemented")
        yield  # Make this a generator (unreachable)


