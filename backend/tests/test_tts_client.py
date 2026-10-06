import io
import wave
from array import array
from types import SimpleNamespace

from app.services import tts_client

TEXT = "Revenue rose sharply this quarter."  # 5 words


def _pcm(seconds: float, amplitude: int = 8000) -> bytes:
    return array("h", [amplitude] * round(seconds * tts_client.SAMPLE_RATE)).tobytes()


class _FakeClient:
    """Stands in for the OpenAI client: returns the scripted audio payloads in order and
    records every request."""

    def __init__(self, payloads):
        self._payloads = list(payloads)
        self.calls = []
        self.audio = SimpleNamespace(speech=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(content=self._payloads.pop(0))


def test_audio_of_plausible_length_passes():
    assert tts_client.check_audio(_pcm(2.0), TEXT) is None


def test_silent_audio_is_flagged():
    assert "silent" in tts_client.check_audio(_pcm(2.0, amplitude=0), TEXT)
    assert "silent" in tts_client.check_audio(b"", TEXT)


def test_audio_too_short_for_the_text_is_flagged():
    assert "cut short" in tts_client.check_audio(_pcm(0.5), TEXT)


def test_synthesize_returns_a_wav_with_its_duration():
    client = _FakeClient([_pcm(2.0)])

    clip = tts_client.synthesize(TEXT, client=client)

    assert (clip.duration_ms, clip.warning) == (2000, None)
    with wave.open(io.BytesIO(clip.wav), "rb") as wav:
        assert (wav.getnchannels(), wav.getframerate(), wav.getnframes()) == (1, 24_000, 48_000)
    assert client.calls[0]["input"] == TEXT
    assert client.calls[0]["response_format"] == "pcm"


def test_incomplete_audio_is_retried_once():
    client = _FakeClient([_pcm(2.0, amplitude=0), _pcm(2.0)])

    clip = tts_client.synthesize(TEXT, client=client)

    assert len(client.calls) == 2
    assert clip.warning is None


def test_audio_still_incomplete_after_retrying_is_returned_with_a_warning():
    client = _FakeClient([_pcm(0.5), _pcm(0.5)])

    clip = tts_client.synthesize(TEXT, client=client)

    assert len(client.calls) == tts_client.MAX_ATTEMPTS
    assert "cut short" in clip.warning


def test_clip_filename_depends_only_on_the_text():
    assert tts_client.clip_filename(TEXT) == tts_client.clip_filename(TEXT)
    assert tts_client.clip_filename(TEXT) != tts_client.clip_filename(TEXT + " Again.")
    assert tts_client.clip_filename(TEXT).endswith(".wav")
