"""
OpenRouter API provider implementation.

OpenRouter provides access to many models (Claude, GPT-4, Llama, etc.)
via an OpenAI-compatible API.
"""

from __future__ import annotations

import json as _json
import os as _os
import typing as _typing

import httpx as _httpx

import brynhild.api.base as base
import brynhild.api.types as types
import brynhild.constants as _constants


class OpenRouterAPIError(Exception):
    """Error from OpenRouter API with structured information."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        error_type: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_type = error_type


def _translate_http_error(error: _httpx.HTTPStatusError) -> OpenRouterAPIError:
    """Translate an httpx HTTP error to a user-friendly error message."""
    status = error.response.status_code

    # Try to parse error body for more details
    error_detail = ""
    error_type = None
    try:
        body = error.response.json()
        if "error" in body:
            err = body["error"]
            error_detail = err.get("message", "")
            error_type = err.get("type")
    except Exception:
        error_detail = error.response.text[:200] if error.response.text else ""

    # Map common status codes to user-friendly messages
    if status == 400:
        msg = f"Bad request: {error_detail or 'Invalid request parameters'}"
    elif status == 401:
        msg = "Authentication failed. Check your OPENROUTER_API_KEY."
    elif status == 402:
        msg = "Payment required. Check your OpenRouter account balance or limits."
    elif status == 403:
        msg = f"Access forbidden: {error_detail or 'Model may not be available for your account'}"
    elif status == 404:
        msg = f"Not found: {error_detail or 'Invalid endpoint or model not found'}"
    elif status == 429:
        msg = "Rate limit exceeded. Please wait and retry."
    elif status == 500:
        msg = "OpenRouter server error. Please try again later."
    elif status == 502:
        msg = "OpenRouter gateway error. The upstream model provider may be unavailable."
    elif status == 503:
        msg = "OpenRouter service temporarily unavailable. Please try again later."
    else:
        msg = f"HTTP {status}: {error_detail or str(error)}"

    return OpenRouterAPIError(msg, status_code=status, error_type=error_type)


# Popular models available on OpenRouter (November 2025)
# Model IDs verified against OpenRouter API
OPENROUTER_MODELS = {
    # Anthropic models
    "anthropic/claude-opus-4.5": "Claude Opus 4.5",
    "anthropic/claude-sonnet-4.5": "Claude Sonnet 4.5",
    "anthropic/claude-opus-4.1": "Claude Opus 4.1",
    "anthropic/claude-haiku-4.5": "Claude Haiku 4.5",
    # OpenAI models
    "openai/gpt-5": "GPT-5",
    "openai/gpt-5-mini": "GPT-5 Mini",
    "openai/gpt-5-codex": "GPT-5 Codex",
    "openai/gpt-oss-120b": "GPT-OSS-120b",
    "openai/gpt-oss-20b": "GPT-OSS-20b",
    # Google models
    "google/gemini-3-pro-preview": "Gemini 3 Pro Preview",
    "google/gemini-2.5-pro": "Gemini 2.5 Pro",
    "google/gemini-2.5-flash": "Gemini 2.5 Flash",
    # xAI models (Grok)
    "x-ai/grok-4.1-fast": "Grok 4.1 Fast",
    "x-ai/grok-4.1-fast:free": "Grok 4.1 Fast",
    "x-ai/grok-4": "Grok 4",
    "x-ai/grok-4-fast": "Grok 4 Fast",
    "x-ai/grok-code-fast-1": "Grok Code Fast 1",
    # DeepSeek models
    "deepseek/deepseek-v3.2-exp": "DeepSeek V3.2 Exp",
    "deepseek/deepseek-v3.1-terminus": "DeepSeek V3.1 Terminus",
    "deepseek/deepseek-chat-v3.1": "DeepSeek V3.1",
    "deepseek/deepseek-r1-0528": "DeepSeek R1 0528",
    "deepseek/deepseek-prover-v2": "DeepSeek Prover V2",
    # Qwen models (Alibaba)
    "qwen/qwen3-max": "Qwen3 Max",
    "qwen/qwen3-235b-a22b": "Qwen3 235B A22B",
    "qwen/qwen3-coder": "Qwen3 Coder 480B A35B",
    "qwen/qwen3-coder-plus": "Qwen3 Coder Plus",
    "qwen/qwen3-coder-flash": "Qwen3 Coder Flash",
    "qwen/qwen3-next-80b-a3b-thinking": "Qwen3 Next 80B Thinking",
    "qwen/qwen3-32b": "Qwen3 32B",
    # Zhipu models (Z.AI / GLM)
    "z-ai/glm-4.6": "GLM 4.6",
    "z-ai/glm-4.5v": "GLM 4.5V",
    # Moonshot models (Kimi)
    "moonshotai/kimi-k2-thinking": "Kimi K2 Thinking",
    "moonshotai/kimi-k2-0905": "Kimi K2 0905",
    "moonshotai/kimi-dev-72b": "Kimi Dev 72B",
    # MiniMax models
    "minimax/minimax-m2": "MiniMax M2",
    # Baidu models (ERNIE)
    "baidu/ernie-4.5-300b-a47b": "ERNIE 4.5 300B",
    "baidu/ernie-4.5-21b-a3b-thinking": "ERNIE 4.5 Thinking",
    # StepFun models
    "stepfun-ai/step3": "Step3",
    # NVIDIA models
    "nvidia/llama-3.1-nemotron-ultra-253b-v1": "Nemotron Ultra 253B",
    "nvidia/llama-3.3-nemotron-super-49b-v1.5": "Nemotron Super 49B",
    # Nous Research models (Hermes)
    "nousresearch/hermes-4-405b": "Hermes 4 405B",
    "nousresearch/hermes-4-70b": "Hermes 4 70B",
    # Mistral models
    "mistralai/mistral-medium-3.1": "Mistral Medium 3.1",
    "mistralai/codestral-2508": "Codestral 2508",
    # Cohere models
    "cohere/command-a": "Command A",
    # Amazon models
    "amazon/nova-premier-v1": "Nova Premier",
    # Perplexity models (search/research)
    "perplexity/sonar-pro-search": "Sonar Pro Search",
    "perplexity/sonar-reasoning-pro": "Sonar Reasoning Pro",
    "perplexity/sonar-deep-research": "Sonar Deep Research",
    # Testing models
    "allenai/olmo-3-32b-think": "OLMo 3 32B Think",
}


class OpenRouterProvider(base.LLMProvider):
    """
    OpenRouter API provider.

    Uses OpenAI-compatible API format with OpenRouter's endpoint.
    """

    BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "openai/gpt-oss-120b",
        site_url: str = "https://example.com/brynhild",
        site_name: str = "Brynhild",
        require_data_policy: bool = True,
    ) -> None:
        """
        Initialize the OpenRouter provider.

        Args:
            api_key: OpenRouter API key (defaults to OPENROUTER_API_KEY env var)
            model: Model to use (e.g., 'anthropic/claude-sonnet-4')
            site_url: URL of your site (required by OpenRouter for rankings)
            site_name: Name of your app (shown in OpenRouter activity)
            require_data_policy: If True, only use providers that respect
                data collection denial (won't train on or log prompts).
        """
        self._api_key = api_key or _os.environ.get("OPENROUTER_API_KEY")
        if not self._api_key:
            raise ValueError(
                "OpenRouter API key required. Set OPENROUTER_API_KEY environment variable "
                "or pass api_key parameter."
            )
        self._model = model
        self._site_url = site_url
        self._site_name = site_name
        self._require_data_policy = require_data_policy

        self._client = _httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "HTTP-Referer": self._site_url,
                "X-Title": self._site_name,
                "User-Agent": "Brynhild/1.0",
                "Content-Type": "application/json",
            },
            timeout=120.0,  # Longer timeout for slower models
        )

    @property
    def name(self) -> str:
        return "openrouter"

    @property
    def model(self) -> str:
        return self._model

    def supports_reasoning(self) -> bool:
        """Check if the model supports reasoning/thinking traces.

        Models that support the `include_reasoning` parameter will return
        reasoning traces in the response.
        """
        # TODO: Replace hardcoded lists with dynamic lookup from OpenRouter's
        # /models endpoint. Cache the model metadata at startup or lazily.
        # See also: supports_tools() has the same issue.
        # Models known to support reasoning (from OpenRouter API metadata)
        REASONING_MODELS = {
            "openai/gpt-oss-120b",
            "openai/gpt-oss-120b:exacto",
            "openai/gpt-oss-20b",
            "openai/gpt-oss-20b:free",
            "openai/gpt-oss-safeguard-20b",
            # DeepSeek models with reasoning
            "deepseek/deepseek-r1",
            "deepseek/deepseek-r1-distill-llama-70b",
            "deepseek/deepseek-r1-distill-qwen-32b",
            # Allen AI OLMo thinking models
            "allenai/olmo-3-32b-think",
            "allenai/olmo-3-7b-think",
        }
        return self._model in REASONING_MODELS

    def supports_tools(self) -> bool:
        """Check if the model supports tool use.

        Most models on OpenRouter support tools. We maintain a blocklist
        of known models that don't support tools based on OpenRouter's API
        metadata (supported_parameters lacking 'tools').
        """
        # Models known NOT to support tools (from OpenRouter API metadata)
        NO_TOOLS_MODELS = {
            # Specialized models
            "deepseek/deepseek-prover-v2",  # Math prover
            "moonshotai/kimi-dev-72b",  # Dev model
            # Chinese models without tool support
            "baidu/ernie-4.5-300b-a47b",
            "baidu/ernie-4.5-21b-a3b-thinking",
            # Some NVIDIA models
            "nvidia/llama-3.1-nemotron-ultra-253b-v1",
            # Search-focused models (use native search, not function calling)
            "cohere/command-a",
            "perplexity/sonar-pro-search",
            "perplexity/sonar-reasoning-pro",
            "perplexity/sonar-deep-research",
            # Open models without tool training
            "allenai/olmo-3-32b-think",
        }
        return self._model not in NO_TOOLS_MODELS

    @property
    def default_reasoning_format(self) -> base.ReasoningFormat:
        """OpenRouter's recommended format for reasoning is a separate field."""
        return "reasoning_field"

    def _get_reasoning_format(self) -> base.ReasoningFormat:
        """Get the reasoning format to use, checking user override first."""
        import brynhild.config as config

        try:
            settings = config.Settings()
            if settings.reasoning_format != "auto":
                # User has explicitly set a format
                return settings.reasoning_format
        except Exception:
            pass  # Fall back to provider default if settings unavailable

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

        try:
            response = await self._client.post("/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()
        except _httpx.HTTPStatusError as e:
            raise _translate_http_error(e) from e
        except _httpx.RequestError as e:
            raise OpenRouterAPIError(
                f"Network error connecting to OpenRouter: {e}"
            ) from e

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

        try:
            async with self._client.stream("POST", "/chat/completions", json=payload) as response:
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

                        # Reasoning/thinking content (various model formats)
                        # DeepSeek uses "reasoning_content", some use "reasoning"
                        reasoning = delta.get("reasoning_content") or delta.get("reasoning")
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

                    # Usage info
                    if "usage" in data:
                        usage_data = data["usage"]
                        yield types.StreamEvent(
                            type="message_delta",
                            usage=types.Usage(
                                input_tokens=usage_data.get("prompt_tokens", 0),
                                output_tokens=usage_data.get("completion_tokens", 0),
                            ),
                        )
        except _httpx.HTTPStatusError as e:
            raise _translate_http_error(e) from e
        except _httpx.RequestError as e:
            raise OpenRouterAPIError(
                f"Network error connecting to OpenRouter: {e}"
            ) from e

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
            payload["tool_choice"] = "auto"

        # Enable reasoning traces for supported models
        if self.supports_reasoning():
            payload["include_reasoning"] = True

        # Provider preferences
        provider_prefs: dict[str, _typing.Any] = {}
        if self._require_data_policy:
            # Only use providers that respect data collection denial
            # (won't train on or log prompts)
            provider_prefs["data_collection"] = "deny"

        if provider_prefs:
            payload["provider"] = provider_prefs

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
                        # OpenRouter convention - separate field
                        assistant_msg["reasoning"] = msg["reasoning"]
                    elif reasoning_format == "thinking_tags":
                        # Wrap in tags in content
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

        # Extract reasoning/thinking content (various model formats)
        thinking = (
            message.get("reasoning_content")
            or message.get("reasoning")
            or None
        )

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

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()
