# Generates speech for a saved narration script, one clip per line, against the real
# API. Costs real money (roughly $0.015 per minute of audio), so this is run by hand,
# not by the test suite.
#
# Usage: python scripts/synthesize_sample.py path/to/<name>.narration.json
#          [--minutes 4.5] [--voice sage] [--force] [--dry-run]
#
# Clips are saved to `<name>.audio/` next to the script, named after each line's text
# (see tts_client.clip_filename), so:
# - lines that already have a clip are skipped - rerunning after a partial run, or with
#   a larger --minutes, only pays for what's missing;
# - every saved narration of the same report shares the directory, and a line reworded
#   by a later run simply has no clip until this is run again.
# The dev sample endpoint (app/routers/dev_samples.py) serves whatever is there.
#
# --minutes limits how much of the script is voiced, counted from the first line at an
# estimated speaking rate: a demo rarely plays to the end, and lines without a clip
# still play with timed captions.
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.logging import configure_logging
from app.core.pricing import calculate_tts_cost
from app.models.narration import NarrationResponse
from app.services import tts_client

ESTIMATED_WORDS_PER_MINUTE = 150


def _lines_within(texts: list[str], minutes: float) -> int:
    """How many leading lines fit in `minutes` of estimated speech (always at least one)."""
    budget_words = minutes * ESTIMATED_WORDS_PER_MINUTE
    words = 0
    for count, text in enumerate(texts, start=1):
        words += len(text.split())
        if words > budget_words and count > 1:
            return count - 1
    return len(texts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate speech clips for a saved narration script.")
    parser.add_argument("narration_path", type=Path)
    parser.add_argument("--minutes", type=float, default=4.5, help="voice roughly this much of the script (default 4.5)")
    parser.add_argument("--voice", default=tts_client.DEFAULT_VOICE)
    parser.add_argument("--force", action="store_true", help="regenerate clips that already exist (e.g. to change voice)")
    parser.add_argument("--dry-run", action="store_true", help="show what would be generated and the estimated cost")
    args = parser.parse_args()

    configure_logging()
    narration = NarrationResponse.model_validate(json.loads(args.narration_path.read_text()))
    texts = [line.text for line in narration.lines]
    selected = texts[: _lines_within(texts, args.minutes)]

    sample_name = args.narration_path.name.split(".narration")[0]
    audio_dir = args.narration_path.with_name(f"{sample_name}.audio")
    pending = [
        (number, text)
        for number, text in enumerate(selected, start=1)
        if args.force or not (audio_dir / tts_client.clip_filename(text)).exists()
    ]

    pending_words = sum(len(text.split()) for _, text in pending)
    estimated_ms = round(pending_words / ESTIMATED_WORDS_PER_MINUTE * 60_000)
    estimated_cost = calculate_tts_cost(sum(len(text) for _, text in pending), estimated_ms)
    print(
        f"Lines 1-{len(selected)} of {len(texts)} selected; {len(pending)} to generate "
        f"({len(selected) - len(pending)} already saved), about {estimated_ms / 60_000:.1f} min of audio, "
        f"estimated ${estimated_cost:.3f}."
    )
    if args.dry_run or not pending:
        return

    audio_dir.mkdir(exist_ok=True)
    total_ms = 0
    total_cost = 0.0
    flagged: list[int] = []
    for number, text in pending:
        clip = tts_client.synthesize(text, voice=args.voice)
        (audio_dir / tts_client.clip_filename(text)).write_bytes(clip.wav)
        total_ms += clip.duration_ms
        total_cost += calculate_tts_cost(len(text), clip.duration_ms)
        note = f"  !! {clip.warning}" if clip.warning else ""
        print(f"{number:>2}. {clip.duration_ms / 1000:>5.1f}s  {text[:70]}{note}")
        if clip.warning:
            flagged.append(number)

    print(
        f"\n{len(pending)} clips, {total_ms / 60_000:.1f} min of audio, estimated ${total_cost:.3f} "
        f"(retries not included) -> saved to {audio_dir}"
    )
    if flagged:
        print(f"Listen to lines {flagged} - their audio still looked incomplete after a retry.")


if __name__ == "__main__":
    main()
