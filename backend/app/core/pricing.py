# Per-model USD pricing, per million tokens.
PRICING = {
    "gpt-5.6-luna": {"input_per_mtok": 0.20, "output_per_mtok": 1.20},
}

# Built-in web search, all models: $10 per 1k calls. The search content it pulls into
# context is billed separately as ordinary input tokens, which the response's usage
# already counts - so only the per-call fee needs adding on top of calculate_cost().
WEB_SEARCH_COST_PER_CALL = 10.00 / 1000


# gpt-4o-mini-tts: $0.60 per million input text tokens and $12 per million audio output
# tokens. The speech endpoint doesn't report token usage, so cost is estimated from what
# can be measured: about 4 characters per text token, and OpenAI's own figure of roughly
# $0.015 per minute of generated audio.
TTS_INPUT_COST_PER_CHAR = 0.60 / 1_000_000 / 4
TTS_COST_PER_AUDIO_MINUTE = 0.015


def calculate_tts_cost(input_chars: int, audio_ms: int) -> float:
    return input_chars * TTS_INPUT_COST_PER_CHAR + (audio_ms / 60_000) * TTS_COST_PER_AUDIO_MINUTE


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    rates = PRICING.get(model)
    if rates is None:
        raise KeyError(f"No pricing configured for model '{model}'")
    return (input_tokens / 1_000_000) * rates["input_per_mtok"] + (
        output_tokens / 1_000_000
    ) * rates["output_per_mtok"]


def calculate_web_search_cost(call_count: int) -> float:
    return call_count * WEB_SEARCH_COST_PER_CALL
