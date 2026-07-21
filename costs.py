"""
costs.py
--------
A rough, honest estimate of what each generation costs in real money, so the
tool doesn't feel like a black box. Uses the standard (non-introductory)
per-model prices, in US dollars per million tokens, so the numbers stay
accurate even after any introductory pricing window ends.

Prompt caching changes the real cost: a cache WRITE costs about 1.25x the
normal input price (5-minute default TTL), and a cache READ costs about
0.1x. We apply those multipliers so the estimate matches what you're
actually billed, not just a naive input+output calculation.
"""

# $ per 1,000,000 tokens: (input, output)
PRICING = {
    "claude-opus-4-8": (5.00, 25.00),
    "claude-sonnet-5": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
}

CACHE_WRITE_MULTIPLIER = 1.25
CACHE_READ_MULTIPLIER = 0.10


def estimate_cost(model_id: str, usage) -> float:
    """Estimate the dollar cost of one API response given its `usage` object."""
    input_price, output_price = PRICING.get(model_id, PRICING["claude-sonnet-5"])

    input_tokens = getattr(usage, "input_tokens", 0) or 0
    output_tokens = getattr(usage, "output_tokens", 0) or 0
    cache_write_tokens = getattr(usage, "cache_creation_input_tokens", 0) or 0
    cache_read_tokens = getattr(usage, "cache_read_input_tokens", 0) or 0

    cost = (
        input_tokens * input_price
        + output_tokens * output_price
        + cache_write_tokens * input_price * CACHE_WRITE_MULTIPLIER
        + cache_read_tokens * input_price * CACHE_READ_MULTIPLIER
    ) / 1_000_000

    return cost


def format_cost(dollars: float) -> str:
    """Human-friendly formatting: cents show more precision than dollars."""
    if dollars < 0.01:
        return f"${dollars:.4f}"
    return f"${dollars:.2f}"
