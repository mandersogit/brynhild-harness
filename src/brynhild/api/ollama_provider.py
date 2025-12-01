"""
Ollama API provider implementation.

Ollama provides local model inference via an OpenAI-compatible API.
Supports both local servers and remote Ollama instances.
"""

from __future__ import annotations

import json as _json
import os as _os
import typing as _typing

import httpx as _httpx

import brynhild.api.base as base
import brynhild.api.types as types
import brynhild.constants as _constants


class OllamaProvider(base.LLMProvider):
    """
    Ollama API provider.

    Uses OpenAI-compatible API format with Ollama's endpoint.
    Supports BRYNHILD_OLLAMA_HOST (preferred) or OLLAMA_HOST (fallback) for remote servers.
    """

    DEFAULT_HOST = "localhost"
    DEFAULT_PORT = 11434

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        model: str = "llama3",
        timeout: float = 300.0,  # Longer timeout for large models
    ) -> None:
        """
        Initialize the Ollama provider.

        Args:
            host: Ollama server hostname. Defaults to BRYNHILD_OLLAMA_HOST or
                  OLLAMA_HOST env var, or 'localhost'.
            port: Ollama server port. Defaults to 11434.
            model: Model to use. Canonical names (e.g., 'openai/gpt-oss-120b')
                   are translated to Ollama format via model aliases config.
            timeout: Request timeout in seconds (default 300s for large models).
        """
        # Support BRYNHILD_OLLAMA_HOST (preferred) or OLLAMA_HOST (standard Ollama convention)
        env_host = _os.environ.get("BRYNHILD_OLLAMA_HOST") or _os.environ.get(
            "OLLAMA_HOST", ""
        )
        if env_host:
            # OLLAMA_HOST can be "hostname" or "hostname:port" or "http://hostname:port"
            if env_host.startswith("http://") or env_host.startswith("https://"):
                # Full URL provided
                base_url = env_host.rstrip("/")
            elif ":" in env_host:
                # hostname:port format
                base_url = f"http://{env_host}"
            else:
                # Just hostname
                base_url = f"http://{env_host}:{port or self.DEFAULT_PORT}"
        else:
            resolved_host = host or self.DEFAULT_HOST
            resolved_port = port or self.DEFAULT_PORT
            base_url = f"http://{resolved_host}:{resolved_port}"

        self._base_url = base_url
        self._requested_model = model
        self._timeout = timeout

        # Translate model name using config-based aliases
        import brynhild.config.model_aliases as model_aliases
        self._model = model_aliases.translate_model("ollama", model)

        self._client = _httpx.AsyncClient(
            base_url=base_url,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Brynhild/1.0",
            },
            timeout=timeout,
        )

    @property
    def name(self) -> str:
        return "ollama"

    @property
    def model(self) -> str:
        return self._model

    @property
    def base_url(self) -> str:
        """Base URL being used for the Ollama server."""
        return self._base_url

    def supports_tools(self) -> bool:
        """Check if the model supports tool use.

        Many Ollama models support tools via the OpenAI-compatible API.
        This is a conservative default - specific models may vary.
        """
        # Most modern models support tools, but we can't know for sure
        # without querying the model metadata. Default to True and let
        # the API error if not supported.
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
        """Send messages and get a complete response."""
        # Apply model profile if enabled
        effective_system = self.apply_profile_to_system(system) if use_profile else system
        effective_max_tokens = (
            self.apply_profile_to_max_tokens(max_tokens) if use_profile else max_tokens
        )

        payload = self._build_payload(
            messages=messages,
            system=effective_system,
            tools=tools,
            max_tokens=effective_max_tokens,
            stream=False,
        )

        response = await self._client.post("/v1/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()

        return self._parse_response(data)

    async def stream(
        self,
        messages: list[dict[str, _typing.Any]],
        *,
        system: str | None = None,
        tools: list[types.Tool] | None = None,
        max_tokens: int = _constants.DEFAULT_MAX_TOKENS,
        use_profile: bool = True,
    ) -> _typing.AsyncIterator[types.StreamEvent]:
        """Stream messages and yield events."""
        # Apply model profile if enabled
        effective_system = self.apply_profile_to_system(system) if use_profile else system
        effective_max_tokens = (
            self.apply_profile_to_max_tokens(max_tokens) if use_profile else max_tokens
        )

        payload = self._build_payload(
            messages=messages,
            system=effective_system,
            tools=tools,
            max_tokens=effective_max_tokens,
            stream=True,
        )

        # Track accumulated tool calls
        tool_calls: dict[int, dict[str, _typing.Any]] = {}

        async with self._client.stream("POST", "/v1/chat/completions", json=payload) as response:
            response.raise_for_status()

            yield types.StreamEvent(type="message_start")

            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue

                data_str = line[6:]  # Remove "data: " prefix

                if data_str == "[DONE]":
                    # Emit final tool use events if any
                    for tool_call in tool_calls.values():
                        if tool_call.get("function"):
                            try:
                                parsed_args = _json.loads(
                                    tool_call["function"].get("arguments", "{}")
                                )
                            except _json.JSONDecodeError:
                                parsed_args = {}

                            yield types.StreamEvent(
                                type="content_stop",
                                tool_use=types.ToolUse(
                                    id=tool_call.get("id", ""),
                                    name=tool_call["function"].get("name", ""),
                                    input=parsed_args,
                                ),
                            )

                    yield types.StreamEvent(type="message_stop")
                    break

                try:
                    data = _json.loads(data_str)
                except _json.JSONDecodeError:
                    continue

                # Process the chunk
                for choice in data.get("choices", []):
                    delta = choice.get("delta", {})

                    # Text content
                    if "content" in delta and delta["content"]:
                        yield types.StreamEvent(
                            type="text_delta",
                            text=delta["content"],
                        )

                    # Tool calls
                    if "tool_calls" in delta:
                        for tc in delta["tool_calls"]:
                            idx = tc.get("index", 0)

                            if idx not in tool_calls:
                                tool_calls[idx] = {
                                    "id": tc.get("id", ""),
                                    "function": {"name": "", "arguments": ""},
                                }
                                yield types.StreamEvent(type="tool_use_start")

                            if "id" in tc and tc["id"]:
                                tool_calls[idx]["id"] = tc["id"]

                            if "function" in tc:
                                func = tc["function"]
                                if "name" in func:
                                    tool_calls[idx]["function"]["name"] = func["name"]
                                if "arguments" in func:
                                    tool_calls[idx]["function"]["arguments"] += func["arguments"]
                                    yield types.StreamEvent(
                                        type="tool_use_delta",
                                        tool_input_delta=func["arguments"],
                                    )

                    # Finish reason
                    if choice.get("finish_reason"):
                        yield types.StreamEvent(
                            type="message_delta",
                            stop_reason=choice["finish_reason"],
                        )

                # Usage info (Ollama may include this in final chunk)
                if "usage" in data:
                    usage_data = data["usage"]
                    yield types.StreamEvent(
                        type="message_delta",
                        usage=types.Usage(
                            input_tokens=usage_data.get("prompt_tokens", 0),
                            output_tokens=usage_data.get("completion_tokens", 0),
                        ),
                    )

    def _build_payload(
        self,
        messages: list[dict[str, _typing.Any]],
        system: str | None,
        tools: list[types.Tool] | None,
        max_tokens: int,
        stream: bool,
    ) -> dict[str, _typing.Any]:
        """Build the request payload."""
        # Format messages for OpenAI API
        formatted_messages = self._format_messages(messages, system)

        payload: dict[str, _typing.Any] = {
            "model": self._model,
            "messages": formatted_messages,
            "max_tokens": max_tokens,
            "stream": stream,
        }

        if tools:
            payload["tools"] = [t.to_openai_format() for t in tools]

        return payload

    def _format_messages(
        self,
        messages: list[dict[str, _typing.Any]],
        system: str | None,
    ) -> list[dict[str, _typing.Any]]:
        """Format messages for OpenAI-compatible API."""
        formatted: list[dict[str, _typing.Any]] = []

        # Add system message if provided
        if system:
            formatted.append({"role": "system", "content": system})

        for msg in messages:
            role = msg["role"]
            content = msg.get("content", "")

            if role == "user":
                formatted.append({"role": "user", "content": str(content)})

            elif role == "assistant":
                assistant_msg: dict[str, _typing.Any] = {"role": "assistant"}

                # Check for tool calls in the assistant message
                if "tool_calls" in msg:
                    assistant_msg["tool_calls"] = msg["tool_calls"]
                    if content:
                        assistant_msg["content"] = str(content)
                else:
                    assistant_msg["content"] = str(content)

                formatted.append(assistant_msg)

            elif role == "tool_result":
                # OpenAI format for tool results
                formatted.append(
                    {
                        "role": "tool",
                        "tool_call_id": msg.get("tool_use_id", ""),
                        "content": str(content),
                    }
                )

        return formatted

    def _parse_response(self, data: dict[str, _typing.Any]) -> types.CompletionResponse:
        """Parse a non-streaming response."""
        choice = data["choices"][0]
        message = choice["message"]

        # Extract text content
        content = message.get("content", "") or ""

        # Extract tool uses
        tool_uses: list[types.ToolUse] = []
        for tc in message.get("tool_calls", []):
            func = tc.get("function", {})
            try:
                args = _json.loads(func.get("arguments", "{}"))
            except _json.JSONDecodeError:
                args = {}

            tool_uses.append(
                types.ToolUse(
                    id=tc.get("id", ""),
                    name=func.get("name", ""),
                    input=args,
                )
            )

        # Usage info
        usage_data = data.get("usage", {})
        usage = types.Usage(
            input_tokens=usage_data.get("prompt_tokens", 0),
            output_tokens=usage_data.get("completion_tokens", 0),
        )

        return types.CompletionResponse(
            id=data.get("id", ""),
            content=content,
            stop_reason=choice.get("finish_reason"),
            usage=usage,
            tool_uses=tool_uses,
        )

    async def list_models(self) -> list[dict[str, _typing.Any]]:
        """List available models on the Ollama server.

        Returns:
            List of model info dicts with name, size, modified, etc.
        """
        response = await self._client.get("/api/tags")
        response.raise_for_status()
        data: dict[str, _typing.Any] = response.json()
        models: list[dict[str, _typing.Any]] = data.get("models", [])
        return models

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

