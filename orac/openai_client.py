# openai_client.py
"""
Low-level LLM client helper using ProviderRegistry for multi-provider support.
Uses explicit provider registry instead of automatic environment access.
"""

from __future__ import annotations

import os
import base64
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Tuple, Union
from loguru import logger
from openai import OpenAI

# ---------------------------------------------------------------------#
# Constants                                                            #
# ---------------------------------------------------------------------#
from orac.config import Config, Provider
from .providers import ProviderRegistry

# Note: DEFAULT_MODEL_NAME now comes from Config.get_default_model_name()


# ---------------------------------------------------------------------#
# Usage / cost tracking                                                #
# ---------------------------------------------------------------------#
#
# Pricing snapshot: 2026-05-06 (USD).
# Source: provider-supplied table folded into the project; covers paid-tier
# headline rates including cache-hit rates and active vendor discounts.
# Excludes batch / flex / priority surcharges and audio modalities.
#
# Rates are stored per-token. Helper constructors below convert from the
# per-1M-tokens figures the providers publish.
# ---------------------------------------------------------------------#


@dataclass(frozen=True)
class TokenRate:
    """Per-token USD rate, optionally tiered by prompt length.

    Flat rates leave ``threshold`` and ``long_rate`` unset. Tiered rates
    apply ``long_rate`` once ``prompt_tokens`` exceeds ``threshold``.
    """

    rate: float
    threshold: Optional[int] = None
    long_rate: Optional[float] = None

    def for_prompt(self, prompt_tokens: int) -> float:
        if (
            self.threshold is not None
            and self.long_rate is not None
            and prompt_tokens > self.threshold
        ):
            return self.long_rate
        return self.rate


@dataclass(frozen=True)
class Pricing:
    """Per-token (USD) pricing for a model."""

    input: TokenRate
    output: TokenRate
    cached_input: Optional[TokenRate] = None


def _flat(per_million: float) -> TokenRate:
    return TokenRate(rate=per_million * 1e-6)


def _tiered(
    short_per_million: float,
    long_per_million: float,
    threshold: int = 200_000,
) -> TokenRate:
    return TokenRate(
        rate=short_per_million * 1e-6,
        threshold=threshold,
        long_rate=long_per_million * 1e-6,
    )


# fmt: off
MODEL_PRICING: Dict[str, Pricing] = {
    # ------------------------------------------------------------ OpenAI
    "gpt-5.5":             Pricing(_tiered(5.0, 10.0),  _tiered(30.0, 45.0),  _tiered(0.5, 1.0)),
    "gpt-5.5-pro":         Pricing(_tiered(30.0, 60.0), _tiered(180.0, 270.0)),
    "gpt-5.4":             Pricing(_tiered(2.5, 5.0),   _tiered(15.0, 22.5),  _tiered(0.25, 0.5)),
    "gpt-5.4-mini":        Pricing(_flat(0.75),         _flat(4.5),           _flat(0.075)),
    "gpt-5.4-nano":        Pricing(_flat(0.2),          _flat(1.25),          _flat(0.02)),
    "gpt-5.4-pro":         Pricing(_tiered(30.0, 60.0), _tiered(180.0, 270.0)),
    "gpt-realtime-1.5":    Pricing(_flat(4.0),          _flat(16.0),          _flat(0.4)),
    "gpt-realtime-mini":   Pricing(_flat(0.6),          _flat(2.4),           _flat(0.06)),

    # ------------------------------------------------------------ Anthropic
    "claude-opus-4-7":     Pricing(_flat(5.0),   _flat(25.0), _flat(0.5)),
    "claude-opus-4-6":     Pricing(_flat(5.0),   _flat(25.0), _flat(0.5)),
    "claude-opus-4-5":     Pricing(_flat(5.0),   _flat(25.0), _flat(0.5)),
    "claude-opus-4-1":     Pricing(_flat(15.0),  _flat(75.0), _flat(1.5)),
    "claude-opus-4":       Pricing(_flat(15.0),  _flat(75.0), _flat(1.5)),
    "claude-sonnet-4-6":   Pricing(_flat(3.0),   _flat(15.0), _flat(0.3)),
    "claude-sonnet-4-5":   Pricing(_flat(3.0),   _flat(15.0), _flat(0.3)),
    "claude-sonnet-4":     Pricing(_flat(3.0),   _flat(15.0), _flat(0.3)),
    "claude-haiku-4-5":    Pricing(_flat(1.0),   _flat(5.0),  _flat(0.1)),
    "claude-haiku-3-5":    Pricing(_flat(0.8),   _flat(4.0),  _flat(0.08)),
    "claude-haiku-3":      Pricing(_flat(0.25),  _flat(1.25), _flat(0.03)),

    # ------------------------------------------------------------ Google
    "gemini-3.1-pro-preview":         Pricing(_tiered(2.0, 4.0),    _tiered(12.0, 18.0), _tiered(0.2, 0.4)),
    "gemini-3.1-flash-lite-preview":  Pricing(_flat(0.25),          _flat(1.5),          _flat(0.025)),
    "gemini-3-flash-preview":         Pricing(_flat(0.5),           _flat(3.0),          _flat(0.05)),
    "gemini-2.5-pro":                 Pricing(_tiered(1.25, 2.5),   _tiered(10.0, 15.0), _tiered(0.125, 0.25)),
    "gemini-2.5-flash":               Pricing(_flat(0.3),           _flat(2.5),          _flat(0.03)),
    "gemini-2.5-flash-lite":          Pricing(_flat(0.1),           _flat(0.4),          _flat(0.01)),

    # ------------------------------------------------------------ xAI
    "grok-4.3":                       Pricing(_flat(1.25), _flat(2.5), _flat(0.2)),
    "grok-4.20-multi-agent-0309":     Pricing(_flat(1.25), _flat(2.5), _flat(0.2)),
    "grok-4.20-0309-reasoning":       Pricing(_flat(1.25), _flat(2.5), _flat(0.2)),
    "grok-4.20-0309-non-reasoning":   Pricing(_flat(1.25), _flat(2.5), _flat(0.2)),
    "grok-4-1-fast-reasoning":        Pricing(_flat(0.2),  _flat(0.5), _flat(0.05)),
    "grok-4-1-fast-non-reasoning":    Pricing(_flat(0.2),  _flat(0.5), _flat(0.05)),

    # ------------------------------------------------------------ DeepSeek
    "deepseek-v4-flash":   Pricing(_flat(0.14),  _flat(0.28), _flat(0.0028)),
    "deepseek-v4-pro":     Pricing(_flat(0.435), _flat(0.87), _flat(0.003625)),

    # ------------------------------------------------------------ Z.AI (GLM)
    "glm-5.1":             Pricing(_flat(1.4), _flat(4.4), _flat(0.26)),
    "glm-5":               Pricing(_flat(1.0), _flat(3.2), _flat(0.2)),
    "glm-5-turbo":         Pricing(_flat(1.2), _flat(4.0), _flat(0.24)),
    "glm-4.7":             Pricing(_flat(0.6), _flat(2.2), _flat(0.11)),
    "glm-4.7-flashx":      Pricing(_flat(0.07), _flat(0.4), _flat(0.01)),
    "glm-4.6":             Pricing(_flat(0.6), _flat(2.2), _flat(0.11)),
    "glm-4.5":             Pricing(_flat(0.6), _flat(2.2), _flat(0.11)),
    "glm-4.5-x":           Pricing(_flat(2.2), _flat(8.9), _flat(0.45)),
    "glm-4.5-air":         Pricing(_flat(0.2), _flat(1.1), _flat(0.03)),
    "glm-4.5-airx":        Pricing(_flat(1.1), _flat(4.5), _flat(0.22)),
}
# fmt: on


_OPENROUTER_VENDOR_PREFIXES: Tuple[str, ...] = (
    "anthropic/", "openai/", "google/", "deepseek/",
    "z-ai/", "z.ai/", "zai/", "x-ai/", "xai/",
)


def _normalize_model_name(model_name: str) -> str:
    """Normalize for pricing lookup: strip vendor prefix and route suffix."""
    name = (model_name or "").strip().lower()
    for prefix in _OPENROUTER_VENDOR_PREFIXES:
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    # Strip OpenRouter-style ":beta", ":thinking", ":free" suffixes.
    name = name.split(":", 1)[0]
    return name


# ---------------------------------------------------------------------#
# Reasoning / thinking knob translation                                #
# ---------------------------------------------------------------------#

# User-facing values follow the OpenAI Responses API vocabulary.
_VALID_EFFORT_VALUES: set[str] = {"none", "minimal", "low", "medium", "high", "xhigh"}

# Effort → Anthropic extended-thinking budget_tokens mapping.
# Anthropic rejects budget_tokens below 1024, so that is the floor.
_ANTHROPIC_EFFORT_BUDGETS: Dict[str, int] = {
    "none": 0,
    "minimal": 1024,
    "low": 1024,
    "medium": 4096,
    "high": 16000,
    "xhigh": 32000,
}

# DeepSeek's OpenAI-compat shim accepts only {"high", "max"}.
_DEEPSEEK_EFFORT_MAP: Dict[str, str] = {
    "none": "high",
    "minimal": "high",
    "low": "high",
    "medium": "high",
    "high": "high",
    "xhigh": "max",
}


def _apply_reasoning_knobs(
    req: Dict[str, Any],
    provider: Optional[Provider],
    model_name: str,
    *,
    thinking: Optional[bool] = None,
    reasoning_effort: Optional[str] = None,
) -> None:
    """Mutate *req* to apply unified thinking/reasoning_effort knobs per provider.

    User-facing values follow the OpenAI Responses API vocabulary:
        reasoning_effort ∈ {"none", "minimal", "low", "medium", "high", "xhigh"}
        thinking ∈ {True, False}

    Per-provider translation:
        OpenAI     → top-level `reasoning_effort`; thinking=False → effort="none"
        DeepSeek   → top-level `reasoning_effort` clamped to {"high","max"};
                     thinking → extra_body.thinking = {"type": "enabled"|"disabled"}
        Anthropic  → extra_body.thinking = {"type":"enabled","budget_tokens":N}
                     where N is mapped from effort; thinking=False omits the block
        Google     → top-level `reasoning_effort`; thinking=False sets
                     extra_body.extra_body.google.thinking_config.thinking_budget=0
        Others     → passthrough `reasoning_effort` + extra_body.thinking
    """
    if thinking is None and reasoning_effort is None:
        return

    if reasoning_effort is not None and reasoning_effort not in _VALID_EFFORT_VALUES:
        logger.warning(
            f"Invalid reasoning_effort '{reasoning_effort}'; "
            f"expected one of {sorted(_VALID_EFFORT_VALUES)}. Ignoring."
        )
        reasoning_effort = None

    extra_body: Dict[str, Any] = req.setdefault("extra_body", {})

    if provider == Provider.OPENAI:
        if reasoning_effort:
            req["reasoning_effort"] = reasoning_effort
        elif thinking is False:
            req["reasoning_effort"] = "none"

    elif provider == Provider.DEEPSEEK:
        if thinking is not None:
            extra_body["thinking"] = {"type": "enabled" if thinking else "disabled"}
        if reasoning_effort:
            req["reasoning_effort"] = _DEEPSEEK_EFFORT_MAP[reasoning_effort]

    elif provider == Provider.ANTHROPIC:
        if thinking is False:
            pass
        elif thinking is True or reasoning_effort:
            budget = _ANTHROPIC_EFFORT_BUDGETS.get(reasoning_effort or "medium", 4096)
            if budget > 0:
                extra_body["thinking"] = {
                    "type": "enabled",
                    "budget_tokens": budget,
                }

    elif provider == Provider.GOOGLE:
        if reasoning_effort:
            req["reasoning_effort"] = reasoning_effort
        if thinking is False:
            google_cfg = extra_body.setdefault("extra_body", {}).setdefault("google", {})
            google_cfg["thinking_config"] = {"thinking_budget": 0}

    else:
        if reasoning_effort:
            req["reasoning_effort"] = reasoning_effort
        if thinking is not None:
            extra_body["thinking"] = {"type": "enabled" if thinking else "disabled"}

    if not extra_body:
        req.pop("extra_body", None)


def _lookup_pricing(model_name: str) -> Optional[Pricing]:
    """Find pricing for *model_name*, trying prefix matches for versioned names."""
    name = _normalize_model_name(model_name)
    if name in MODEL_PRICING:
        return MODEL_PRICING[name]
    # Try prefix match (e.g. "gpt-5.4-2026-01-01" → "gpt-5.4")
    for key in sorted(MODEL_PRICING, key=len, reverse=True):
        if name.startswith(key):
            return MODEL_PRICING[key]
    return None


def _compute_cost(
    pricing: Pricing,
    prompt_tokens: int,
    cached_tokens: int,
    completion_tokens: int,
) -> float:
    """Total USD cost given tokens and pricing.

    Cached tokens are billed at the cache rate; the remaining prompt tokens
    pay the standard input rate. If a model has no cache rate listed, all
    prompt tokens are billed at the input rate.
    """
    cached_tokens = max(0, min(cached_tokens, prompt_tokens))
    uncached = prompt_tokens - cached_tokens
    cost = uncached * pricing.input.for_prompt(prompt_tokens)
    if cached_tokens:
        cache_rate = pricing.cached_input or pricing.input
        cost += cached_tokens * cache_rate.for_prompt(prompt_tokens)
    cost += completion_tokens * pricing.output.for_prompt(prompt_tokens)
    return cost


@dataclass
class Usage:
    """Token usage and optional cost for a single API call."""
    prompt_tokens: int = 0
    cached_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model: str = ""
    cost: Optional[float] = None

    def __add__(self, other: "Usage") -> "Usage":
        """Accumulate usage across multiple calls."""
        combined_cost: Optional[float] = None
        if self.cost is not None and other.cost is not None:
            combined_cost = self.cost + other.cost
        elif self.cost is not None:
            combined_cost = self.cost
        elif other.cost is not None:
            combined_cost = other.cost
        return Usage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            cached_tokens=self.cached_tokens + other.cached_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            model=other.model or self.model,
            cost=combined_cost,
        )


@dataclass
class CompletionResult:
    """Wraps an LLM response with optional usage/cost metadata."""
    text: str
    usage: Optional[Usage] = None

    # Allow transparent use as a string in most contexts
    def __str__(self) -> str:
        return self.text


# ---------------------------------------------------------------------#
# Helpers                                                              #
# ---------------------------------------------------------------------#


def _encode_file_to_base64(file_path: str) -> str:
    """Encode a file to base64 string."""
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _get_mime_type(file_path: str) -> str:
    """Get MIME type based on file extension."""
    ext = file_path.lower().split(".")[-1]
    mime_types = {
        "pdf": "application/pdf",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "gif": "image/gif",
        "webp": "image/webp",
        "txt": "text/plain",
        "md": "text/markdown",
        "py": "text/plain",
        "js": "text/plain",
        "json": "application/json",
        "csv": "text/csv",
        "html": "text/html",
        "xml": "text/xml",
    }
    return mime_types.get(ext, "text/plain")


def _gai_to_openai_messages(
    history: List[Dict[str, Any]],
    system_prompt: Optional[str],
    file_paths: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Translate the project's message format ({role,text/parts}) into
    OpenAI's {role,content} list with file attachments.
    """
    msgs: List[Dict[str, Any]] = []
    if system_prompt:
        msgs.append({"role": "system", "content": system_prompt})

    for i, msg in enumerate(history):
        role = msg.get("role")
        if role not in ("user", "model"):
            raise ValueError(
                f"Invalid role '{role}' at message {i}; expected 'user' or 'model'."
            )
        text = msg.get("text")
        parts = msg.get("parts")
        if text is None and parts:
            text = "\n".join(map(str, parts))
        if text is None:
            raise ValueError(f"Message {i} is empty.")

        # For the last user message, add files if provided
        if role == "user" and i == len(history) - 1 and file_paths:
            content = [{"type": "text", "text": text}]
            for file_path in file_paths:
                base64_data = _encode_file_to_base64(file_path)
                mime_type = _get_mime_type(file_path)
                data_url = f"data:{mime_type};base64,{base64_data}"
                filename = os.path.basename(file_path)

                # For images, use image_url type; for other files, include as text
                if mime_type.startswith("image/"):
                    content.append(
                        {"type": "image_url", "image_url": {"url": data_url}}
                    )
                # Note: Google hack to send pdfs as image_url type
                elif mime_type == "application/pdf":
                    print("Warning: Sending PDF as image_url type is a Google hack.")
                    content.append(
                        {"type": "image_url", "image_url": {"url": data_url}}
                    )
                else:
                    # For non-image files, use image_url type (Google API requirement)
                    logger.debug(f"Sending {filename} ({mime_type}) as image_url type (Google API workaround)")
                    content.append(
                        {"type": "image_url", "image_url": {"url": data_url}}
                    )
            msgs.append({"role": "user", "content": content})
        else:
            msgs.append(
                {"role": "user" if role == "user" else "assistant", "content": text}
            )
    return msgs


def call_api(
    provider_registry: ProviderRegistry,
    provider: Optional[Provider] = None,  # Use default if None
    *,
    message_history: List[Dict[str, Any]],
    file_paths: Optional[List[str]] = None,
    system_prompt: Optional[str] = None,
    model_name: Optional[str] = None,  # Use provider's model if None
    generation_config: Optional[Dict[str, Any]] = None,
    thinking: Optional[bool] = None,
    reasoning_effort: Optional[str] = None,
) -> CompletionResult:
    """
    Call LLM API using provider registry.
    Supports:
      • chat history + system prompt
      • generation_config passthrough (temperature, max_tokens, etc.)
      • optional file upload (images/docs) via base64 encoding
      • returns `CompletionResult` with the model's top choice and usage data
    """
    client = provider_registry.get_client(provider)

    # Get model name from registry if not specified
    resolved_model_name = model_name or provider_registry.get_model_name(provider)

    # -----------------------------------------------------------------#
    # Build messages with file attachments                            #
    # -----------------------------------------------------------------#
    if file_paths:
        logger.info(f"Encoding {len(file_paths)} file(s) as base64…")
        for path in file_paths:
            logger.debug(f"Encoding {path} as base64 data")

    messages = _gai_to_openai_messages(message_history, system_prompt, file_paths)
    logger.debug(f"Sending {len(messages)} messages to LLM via OpenAI")

    # -----------------------------------------------------------------#
    # Build request                                                    #
    # -----------------------------------------------------------------#
    req: Dict[str, Any] = {
        "model": resolved_model_name,
        "messages": messages,
    }
    if generation_config:
        req.update(generation_config)
    if "max_tokens" in req:
        req["max_completion_tokens"] = req.pop("max_tokens")

    # Translate unified thinking / reasoning_effort knobs per provider.
    resolved_provider = provider or provider_registry.get_default_provider()
    _apply_reasoning_knobs(
        req,
        resolved_provider,
        resolved_model_name,
        thinking=thinking,
        reasoning_effort=reasoning_effort,
    )

    # -----------------------------------------------------------------#
    # Call API                                                         #
    # -----------------------------------------------------------------#
    logger.info(f"Calling model '{resolved_model_name}' via provider '{provider or provider_registry.get_default_provider()}'")
    try:
        response = client.chat.completions.create(**req)
    except Exception as e:
        logger.error(f"LLM API call failed: {e}")
        raise

    # -----------------------------------------------------------------#
    # Extract text and usage                                           #
    # -----------------------------------------------------------------#
    choice = response.choices[0]
    content = getattr(choice.message, "content", "")

    usage: Optional[Usage] = None
    if getattr(response, "usage", None) is not None:
        ru = response.usage
        prompt_tokens = getattr(ru, "prompt_tokens", 0) or 0
        completion_tokens = getattr(ru, "completion_tokens", 0) or 0
        total_tokens = getattr(ru, "total_tokens", 0) or (prompt_tokens + completion_tokens)

        # Cached prompt tokens may appear under different fields depending on
        # the upstream provider (OpenAI: prompt_tokens_details.cached_tokens;
        # Anthropic: cache_read_input_tokens; some shims: cached_tokens).
        cached_tokens = 0
        prompt_details = getattr(ru, "prompt_tokens_details", None)
        if prompt_details is not None:
            cached_tokens = getattr(prompt_details, "cached_tokens", 0) or 0
        if not cached_tokens:
            cached_tokens = (
                getattr(ru, "cache_read_input_tokens", 0)
                or getattr(ru, "cached_tokens", 0)
                or 0
            )

        cost: Optional[float] = None
        pricing = _lookup_pricing(resolved_model_name)
        if pricing:
            cost = _compute_cost(pricing, prompt_tokens, cached_tokens, completion_tokens)

        usage = Usage(
            prompt_tokens=prompt_tokens,
            cached_tokens=cached_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            model=resolved_model_name,
            cost=cost,
        )
        cache_note = f" (cached {cached_tokens})" if cached_tokens else ""
        logger.info(
            f"LLM completion successful — {total_tokens} tokens{cache_note}"
            + (f" (${cost:.6f})" if cost is not None else "")
        )
    else:
        logger.info("LLM completion successful")

    return CompletionResult(text=content, usage=usage)
