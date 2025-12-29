"""
Stub providers for future implementation.

These providers raise NotImplementedError with helpful messages.
They exist to:
1. Reserve the provider type names
2. Provide clear error messages when users try to use them
3. Make it easy to implement them later (just fill in the class)
"""

import brynhild.api.providers.stubs.lmstudio as _lmstudio
import brynhild.api.providers.stubs.openai as _openai
import brynhild.api.providers.stubs.vllm as _vllm

OpenAIProvider = _openai.OpenAIProvider
LMStudioProvider = _lmstudio.LMStudioProvider
VLLMProvider = _vllm.VLLMProvider

__all__ = ["OpenAIProvider", "LMStudioProvider", "VLLMProvider"]
