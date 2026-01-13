"""
Ollama API provider implementation.

Ollama provides local model inference via an OpenAI-compatible API.
Supports both local servers and remote Ollama instances.

⚠️ TEMPORARY ARCHITECTURE: This provider reads config from env vars and constructor args.
Near-term follow-up will refactor to accept ProviderInstanceConfig for full config integration.
"""

from __future__ import annotations

import json as _json
import os as _os
import typing as _typing

import httpx as _httpx

import brynhild.api.base as base
import brynhild.api.types as types
import brynhild.constants as _constants


import brynhild.api.credentials as _credentials


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
        credentials_path: str | None = None,
        api_key: str | None = None,
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
            credentials_path: Path to JSON file containing credentials.
                File may contain {"api_key": "..."} for authenticated Ollama servers.
                Supports ~ and $VAR expansion.
            api_key: API key for authenticated Ollama servers (e.g., cloud-hosted).
                credentials_path takes precedence if both provided.
        """
        # Load credentials from file if provided
        effective_api_key = api_key
        if credentials_path:
            credentials = _credentials.load_credentials_from_path(credentials_path)
            effective_api_key = credentials.get("api_key") or api_key

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

        # Build headers
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "User-Agent": "Brynhild/1.0",
        }
        if effective_api_key:
            headers["Authorization"] = f"Bearer {effective_api_key}"

        self._client = _httpx.AsyncClient(
            base_url=base_url,
            headers=headers,
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

    def supports_reasoning(self) -> bool:
        """Check if the model supports reasoning/thinking.

        Ollama models with thinking support include:
        - GPT-OSS models (gpt-oss-120b, gpt-oss-20b)
        - DeepSeek R1 models
        - Various thinking-enabled variants
        """
        model_lower = self._model.lower()

        # Models known to support thinking/reasoning
        reasoning_patterns = [
            "gpt-oss",
            "deepseek-r1",
            "qwen3",
            "qwen-coder",
            "-think",
            "thinking",
        ]
        return any(pattern in model_lower for pattern in reasoning_patterns)

    def _is_gpt_oss_model(self) -> bool:
        """Check if the model is a GPT-OSS variant (uses string think levels)."""
        return "gpt-oss" in self._model.lower()

    def translate_reasoning_level(
        self,
        level: base.ReasoningLevel | None = None,
    ) -> dict[str, _typing.Any]:
        """
        Translate unified reasoning level to Ollama's `think` parameter.

        For GPT-OSS models: think: "low"|"medium"|"high" (string)
        For other models: think: true|false (boolean)

        Note: GPT-OSS thinking cannot be fully disabled.
        """
        if not self.supports_reasoning():
            return {}

        effective_level = level if level is not None else self.get_reasoning_level()

        # Parse raw prefix
        parsed_level, is_raw = base.parse_reasoning_level(effective_level)

        # "auto" means let the model decide (don't send think parameter)
        if parsed_level == "auto":
            return {}

        if self._is_gpt_oss_model():
            # GPT-OSS uses string levels: "low", "medium", "high"
            # Cannot be fully disabled
            level_map = {
                "off": "low",      # Can't disable, use lowest
                "minimal": "low",
                "low": "low",
                "medium": "medium",
                "high": "high",
                "maximum": "high",
            }

            if is_raw:
                think_value = parsed_level
            else:
                think_value = level_map.get(parsed_level, "medium")

            return {"think": think_value}
        else:
            # Other models use boolean think: true|false
            enable = parsed_level not in ("off", "none")
            return {"think": enable}

    @property
    def default_reasoning_format(self) -> base.ReasoningFormat:
        """Ollama's default - thinking tags is safest for local models."""
        return "thinking_tags"

    def _get_reasoning_format(self) -> base.ReasoningFormat:
        """Get the reasoning format to use, checking user override first."""
        import brynhild.config as config

        try:
            settings = config.Settings()
            if settings.reasoning_format != "auto":
                return settings.reasoning_format
        except Exception:
            pass

        return self.default_reasoning_format

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

                    # Reasoning/thinking content (Ollama uses "reasoning")
                    reasoning = delta.get("reasoning") or delta.get("reasoning_content")
                    if reasoning:
                        yield types.StreamEvent(
                            type="thinking_delta",
                            thinking=reasoning,
                        )

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

        # Request usage data in streaming mode (OpenAI extension)
        if stream:
            payload["stream_options"] = {"include_usage": True}

        if tools:
            payload["tools"] = [t.to_openai_format() for t in tools]

        # Add reasoning level parameters (think control)
        reasoning_params = self.translate_reasoning_level()
        if reasoning_params:
            payload.update(reasoning_params)

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

        # Determine if we should include reasoning in this request.
        # Standard practice: include reasoning during tool loops (so model
        # remembers why it made tool calls), but strip it on subsequent turns
        # (after a final response) to save tokens.
        #
        # Heuristic: if the last message is a tool_result, we're in a tool loop
        # and should keep reasoning. Otherwise, strip it.
        in_tool_loop = messages and messages[-1].get("role") == "tool_result"

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

                # Handle reasoning based on configured format AND whether we're
                # in a tool loop. We preserve reasoning for logging and potential
                # tool access, but only SEND it to the API during tool loops.
                if in_tool_loop and "reasoning" in msg and msg["reasoning"]:
                    reasoning_format = self._get_reasoning_format()
                    if reasoning_format == "reasoning_field":
                        assistant_msg["reasoning"] = msg["reasoning"]
                    elif reasoning_format == "thinking_tags":
                        existing_content = assistant_msg.get("content", "")
                        thinking_wrapped = f"<thinking>{msg['reasoning']}</thinking>"
                        if existing_content:
                            assistant_msg["content"] = f"{thinking_wrapped}\n\n{existing_content}"
                        else:
                            assistant_msg["content"] = thinking_wrapped
                    # else: "none" - don't include reasoning

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

        # Extract reasoning/thinking content (Ollama returns this as "reasoning")
        thinking = message.get("reasoning") or message.get("reasoning_content") or None

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
            thinking=thinking,
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


