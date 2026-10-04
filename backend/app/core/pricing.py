# Per-model USD pricing, per million tokens.
PRICING = {
    "gpt-5.6-luna": {"input_per_mtok": 0.20, "output_per_mtok": 1.20},
}

# Built-in web search, all models: $10 per 1k calls. The search content it pulls into
# context is billed separately as ordinary input tokens, which the response's usage
# already counts - so only the per-call fee needs adding on top of calculate_cost().
WEB_SEARCH_COST_PER_CALL = 10.00 / 1000


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    rates = PRICING.get(model)
    if rates is None:
        raise KeyError(f"No pricing configured for model '{model}'")
    return (input_tokens / 1_000_000) * rates["input_per_mtok"] + (
        output_tokens / 1_000_000
    ) * rates["output_per_mtok"]


def calculate_web_search_cost(call_count: int) -> float:
    return call_count * WEB_SEARCH_COST_PER_CALL
