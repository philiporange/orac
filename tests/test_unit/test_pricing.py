"""Unit tests for cost reporting in orac.openai_client."""

from __future__ import annotations

import pytest

from orac.openai_client import (
    MODEL_PRICING,
    Pricing,
    TokenRate,
    Usage,
    _compute_cost,
    _lookup_pricing,
    _normalize_model_name,
)


class TestTokenRate:
    def test_flat_rate_ignores_threshold(self):
        rate = TokenRate(rate=1e-6)
        assert rate.for_prompt(10) == 1e-6
        assert rate.for_prompt(10_000_000) == 1e-6

    def test_tiered_rate_switches_at_threshold(self):
        rate = TokenRate(rate=1e-6, threshold=200_000, long_rate=2e-6)
        assert rate.for_prompt(199_999) == 1e-6
        assert rate.for_prompt(200_000) == 1e-6
        assert rate.for_prompt(200_001) == 2e-6


class TestNormalizeModelName:
    def test_lowercases_and_strips_whitespace(self):
        assert _normalize_model_name("  GPT-5.4 ") == "gpt-5.4"

    @pytest.mark.parametrize(
        "raw,normalized",
        [
            ("anthropic/claude-opus-4-7", "claude-opus-4-7"),
            ("openai/gpt-5.4-mini", "gpt-5.4-mini"),
            ("google/gemini-3-flash-preview", "gemini-3-flash-preview"),
            ("z-ai/glm-4.6", "glm-4.6"),
            ("z.ai/glm-4.6", "glm-4.6"),
            ("deepseek/deepseek-v4-flash", "deepseek-v4-flash"),
        ],
    )
    def test_strips_openrouter_vendor_prefix(self, raw, normalized):
        assert _normalize_model_name(raw) == normalized

    def test_strips_openrouter_route_suffix(self):
        assert _normalize_model_name("anthropic/claude-opus-4-7:thinking") == "claude-opus-4-7"


class TestLookupPricing:
    def test_exact_match(self):
        assert _lookup_pricing("claude-opus-4-7") is MODEL_PRICING["claude-opus-4-7"]

    def test_prefix_match_for_dated_versions(self):
        # Hypothetical dated alias should still resolve.
        assert _lookup_pricing("gpt-5.4-mini-2026-01-01") is MODEL_PRICING["gpt-5.4-mini"]

    def test_openrouter_format_resolves(self):
        assert _lookup_pricing("anthropic/claude-sonnet-4-6") is MODEL_PRICING["claude-sonnet-4-6"]

    def test_unknown_model_returns_none(self):
        assert _lookup_pricing("model-from-the-future") is None

    def test_default_model_has_pricing(self):
        # The project default model must have a pricing entry so cost
        # reporting doesn't silently drop on out-of-the-box configurations.
        from orac.config import Config
        assert _lookup_pricing(Config.get_default_model_name()) is not None


class TestComputeCost:
    def test_flat_pricing_no_cache(self):
        # gpt-5.4-mini: input $0.75/M, cached $0.075/M, output $4.5/M
        pricing = MODEL_PRICING["gpt-5.4-mini"]
        cost = _compute_cost(pricing, prompt_tokens=1_000_000, cached_tokens=0, completion_tokens=1_000_000)
        assert cost == pytest.approx(0.75 + 4.5)

    def test_cache_hits_billed_at_cache_rate(self):
        pricing = MODEL_PRICING["gpt-5.4-mini"]
        # 1M total prompt tokens, half cached, no completion
        cost = _compute_cost(pricing, prompt_tokens=1_000_000, cached_tokens=500_000, completion_tokens=0)
        # 500k uncached at $0.75/M + 500k cached at $0.075/M
        expected = 0.75 * 0.5 + 0.075 * 0.5
        assert cost == pytest.approx(expected)

    def test_cached_tokens_clamped_to_prompt_tokens(self):
        pricing = MODEL_PRICING["gpt-5.4-mini"]
        # cached > prompt: clamp instead of going negative on uncached
        cost = _compute_cost(pricing, prompt_tokens=1000, cached_tokens=10_000, completion_tokens=0)
        # All 1000 tokens billed at cache rate
        expected = 1000 * 0.075e-6
        assert cost == pytest.approx(expected)

    def test_no_cache_pricing_falls_back_to_input(self):
        # gpt-5.5-pro has cached_input=None — cached tokens should still bill.
        pricing = MODEL_PRICING["gpt-5.5-pro"]
        assert pricing.cached_input is None
        cost = _compute_cost(pricing, prompt_tokens=1000, cached_tokens=400, completion_tokens=0)
        # All 1000 tokens at $30/M (short context)
        expected = 1000 * 30.0e-6
        assert cost == pytest.approx(expected)

    def test_tiered_pricing_short_context(self):
        # gemini-2.5-pro: $1.25/M short, $2.5/M long, threshold 200k.
        pricing = MODEL_PRICING["gemini-2.5-pro"]
        cost = _compute_cost(pricing, prompt_tokens=100_000, cached_tokens=0, completion_tokens=10_000)
        # 100k @ $1.25/M + 10k @ $10/M (short output rate)
        expected = 100_000 * 1.25e-6 + 10_000 * 10.0e-6
        assert cost == pytest.approx(expected)

    def test_tiered_pricing_long_context(self):
        pricing = MODEL_PRICING["gemini-2.5-pro"]
        cost = _compute_cost(pricing, prompt_tokens=300_000, cached_tokens=0, completion_tokens=10_000)
        # 300k @ $2.5/M + 10k @ $15/M (long output rate)
        expected = 300_000 * 2.5e-6 + 10_000 * 15.0e-6
        assert cost == pytest.approx(expected)

    def test_anthropic_cache_discount(self):
        # Claude Opus 4.7: input $5/M, cache $0.5/M, output $25/M
        pricing = MODEL_PRICING["claude-opus-4-7"]
        cost = _compute_cost(pricing, prompt_tokens=10_000, cached_tokens=8_000, completion_tokens=2_000)
        # 2k uncached @ $5/M + 8k cached @ $0.5/M + 2k output @ $25/M
        expected = 2_000 * 5e-6 + 8_000 * 0.5e-6 + 2_000 * 25e-6
        assert cost == pytest.approx(expected)


class TestUsageAccumulation:
    def test_add_combines_token_counts(self):
        a = Usage(prompt_tokens=100, cached_tokens=20, completion_tokens=50, total_tokens=150, model="m1", cost=0.001)
        b = Usage(prompt_tokens=200, cached_tokens=30, completion_tokens=80, total_tokens=280, model="m2", cost=0.002)
        c = a + b
        assert c.prompt_tokens == 300
        assert c.cached_tokens == 50
        assert c.completion_tokens == 130
        assert c.total_tokens == 430
        assert c.cost == pytest.approx(0.003)
        assert c.model == "m2"  # latest wins

    def test_add_handles_partial_cost(self):
        a = Usage(prompt_tokens=10, completion_tokens=10, cost=0.001)
        b = Usage(prompt_tokens=10, completion_tokens=10, cost=None)
        assert (a + b).cost == pytest.approx(0.001)
        assert (b + a).cost == pytest.approx(0.001)
        assert (b + b).cost is None

    def test_default_cached_tokens_is_zero(self):
        u = Usage(prompt_tokens=100, completion_tokens=50)
        assert u.cached_tokens == 0


class TestPricingTableCoverage:
    """Guard rails: every supported provider's headline models are present."""

    @pytest.mark.parametrize(
        "model",
        [
            # OpenAI
            "gpt-5.5", "gpt-5.4", "gpt-5.4-mini", "gpt-5.4-nano",
            # Anthropic
            "claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5",
            # Google
            "gemini-3-flash-preview", "gemini-3.1-pro-preview", "gemini-2.5-pro",
            # xAI
            "grok-4.3",
            # DeepSeek
            "deepseek-v4-flash", "deepseek-v4-pro",
            # Z.AI
            "glm-4.6", "glm-4.5-air",
        ],
    )
    def test_model_has_pricing(self, model):
        assert model in MODEL_PRICING, f"Missing pricing for {model}"
