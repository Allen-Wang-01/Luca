# Per-model USD pricing, per million tokens.
PRICING = {
    "gpt-5.6-luna": {"input_per_mtok": 0.20, "output_per_mtok": 1.20},
}


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    rates = PRICING.get(model)
    if rates is None:
        raise KeyError(f"No pricing configured for model '{model}'")
    return (input_tokens / 1_000_000) * rates["input_per_mtok"] + (
        output_tokens / 1_000_000
    ) * rates["output_per_mtok"]
