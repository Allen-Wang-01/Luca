# Turns one narration line into speech. This is the only module that knows which
# text-to-speech provider is in use: callers hand it text and get back a WAV clip with
# its duration, so swapping the provider or model means changing this file alone.
#
# Audio is requested as raw PCM rather than MP3: the duration is then exact arithmetic
# on the byte count, and silence can be detected by looking at the samples - both
# needed for the checks below - without pulling in an audio-decoding dependency.
import hashlib
import io
import time
import wave
from array import array
from dataclasses import dataclass
from typing import Any

from app.core.logging import get_logger
from app.core.pricing import calculate_tts_cost
from app.services import llm_client

logger = get_logger(__name__)

MODEL = "gpt-4o-mini-tts"
DEFAULT_VOICE = "sage"
INSTRUCTIONS = (
    "Speak as a calm, confident financial advisor walking a client through a company's "
    "results. Keep a measured pace, pronounce figures clearly, and sound warm but professional."
)

# What the API's "pcm" response format contains: 24 kHz, 16-bit signed little-endian, mono.
SAMPLE_RATE = 24_000
SAMPLE_WIDTH_BYTES = 2

# The speech endpoint can return a successful response whose audio is silent or stops
# short of the end of the text. Natural speech runs at roughly 0.35-0.45 seconds per
# word, so a clip well under that has lost part of the line. This catches silence and
# large cuts, not a clipped final word.
MIN_SECONDS_PER_WORD = 0.25
SILENCE_PEAK = 500  # out of 32767
MAX_ATTEMPTS = 2


@dataclass(frozen=True)
class SpeechClip:
    wav: bytes
    duration_ms: int
    # Why the audio looks incomplete, if it still does after retrying; None when it passed.
    warning: str | None


def clip_filename(text: str) -> str:
    """File name for a saved clip, derived from the line's text - so a saved clip is
    only ever played for the exact wording it was generated from."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:20] + ".wav"


def pcm_duration_ms(pcm: bytes) -> int:
    return round(len(pcm) / (SAMPLE_RATE * SAMPLE_WIDTH_BYTES) * 1000)


def check_audio(pcm: bytes, text: str) -> str | None:
    """Returns why the audio looks incomplete for this text, or None if it looks fine."""
    samples = array("h")
    samples.frombytes(pcm[: len(pcm) - len(pcm) % SAMPLE_WIDTH_BYTES])
    if not samples or max(abs(sample) for sample in samples) < SILENCE_PEAK:
        return "audio is silent"

    word_count = len(text.split())
    seconds = pcm_duration_ms(pcm) / 1000
    if word_count and seconds / word_count < MIN_SECONDS_PER_WORD:
        return f"audio is only {seconds:.1f}s for {word_count} words - probably cut short"
    return None


def pcm_to_wav(pcm: bytes) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(SAMPLE_WIDTH_BYTES)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(pcm)
    return buffer.getvalue()


def synthesize(text: str, voice: str = DEFAULT_VOICE, client: Any = None) -> SpeechClip:
    client = client or llm_client.client

    pcm = b""
    warning: str | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        started = time.perf_counter()
        response = client.audio.speech.create(
            model=MODEL,
            voice=voice,
            input=text,
            instructions=INSTRUCTIONS,
            response_format="pcm",
        )
        pcm = response.content
        duration_ms = pcm_duration_ms(pcm)
        warning = check_audio(pcm, text)
        # The endpoint reports no usage, so the cost is an estimate from the audio length.
        logger.info(
            "tts_call attempt=%d chars=%d audio_ms=%d est_cost_usd=%.6f latency_ms=%d warning=%r",
            attempt,
            len(text),
            duration_ms,
            calculate_tts_cost(len(text), duration_ms),
            round((time.perf_counter() - started) * 1000),
            warning,
        )
        if warning is None:
            break

    return SpeechClip(wav=pcm_to_wav(pcm), duration_ms=pcm_duration_ms(pcm), warning=warning)
