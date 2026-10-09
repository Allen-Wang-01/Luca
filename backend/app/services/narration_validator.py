# Checks the model's narration against what it can actually point to: every line's
# target_id must exist in the report, so the frontend sync engine always has something
# real to scroll to and highlight, and every cited URL must have come back from a web
# search in this run, so a source shown to the listener can't be one the model made up,
# and a chart shown with a line must be one the chart tools actually built.
# The model is given the valid ids, but nothing forces it to use them exactly - a
# slightly wrong cell id (e.g. a misspelled col_id) is common and mostly recoverable.
# Pure functions, no I/O.
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.models.narration import (
    LineVisual,
    LLMNarrationLine,
    NarrationLine,
    RemovedSource,
    RemovedVisual,
    Visual,
)

# Sites whose pages are user posts or videos rather than reporting - a real search
# result, but not something to put in front of a listener as a source. Matched as the
# host itself or any subdomain of it.
BLOCKED_SOURCE_DOMAINS = frozenset(
    {
        "reddit.com",
        "youtube.com",
        "youtu.be",
        "x.com",
        "twitter.com",
        "facebook.com",
        "instagram.com",
        "tiktok.com",
        "stocktwits.com",
        "quora.com",
    }
)

# Row and cell ids are `{block_id}__r{row_index}` and `{block_id}__r{row_index}_{col_id}`
# (docs/schema.md), so an invalid id's ancestors can be recovered from the id itself.
_ROW_PREFIX_RE = re.compile(r"^(.+__r\d+)")


class NarrationQualityError(Exception):
    pass


def _ancestors(target_id: str) -> list[str]:
    candidates = []
    row_match = _ROW_PREFIX_RE.match(target_id)
    if row_match:
        candidates.append(row_match.group(1))
    if "__" in target_id:
        candidates.append(target_id.split("__", 1)[0])
    return candidates


def repair_target_ids(
    lines: list[NarrationLine], valid_ids: set[str], fallback_id: str
) -> tuple[list[NarrationLine], int]:
    """Returns (repaired lines, number of lines whose target had to change).

    An invalid target falls back, in order, to its nearest valid ancestor (cell -> row
    -> block), then the previous line's target (narration usually continues discussing
    the same thing), then `fallback_id`. Lines with empty text are dropped.
    """
    repaired: list[NarrationLine] = []
    repair_count = 0
    for line in lines:
        text = line.text.strip()
        if not text:
            continue
        target = line.target_id
        if target not in valid_ids:
            repair_count += 1
            target = next(
                (candidate for candidate in _ancestors(target) if candidate in valid_ids),
                repaired[-1].target_id if repaired else fallback_id,
            )
        repaired.append(line.model_copy(update={"text": text, "target_id": target}))
    return repaired, repair_count


def attach_visuals(
    lines: list[LLMNarrationLine], charts: dict[str, Visual]
) -> tuple[list[NarrationLine], list[RemovedVisual]]:
    """Turns the model's lines into script lines, each carrying the chart it asked for.

    Returns (lines, the chart references that didn't hold up and why). A chart id that
    no chart tool produced is dropped - that includes charts that failed their checks,
    which never got an id. An emphasis key the chart doesn't have is dropped on its own;
    the chart is still shown. A chart is shown for one unbroken run of lines only: when
    it comes back after a line without it, the card would pop up again for something
    the listener has already been walked through, so later runs are dropped. Lines with
    empty text are left out here, so line numbers match the final script.
    """
    attached: list[NarrationLine] = []
    removed: list[RemovedVisual] = []
    shown: set[str] = set()
    for line in lines:
        if not line.text.strip():
            continue
        number = len(attached) + 1
        visual: LineVisual | None = None
        chart = charts.get(line.chart_id) if line.chart_id else None
        previous = attached[-1].visual if attached else None
        if line.chart_id and chart is None:
            removed.append(
                RemovedVisual(
                    line=number,
                    chart_id=line.chart_id,
                    reason="unknown_chart",
                    detail="No chart with this id was built.",
                )
            )
        elif chart is not None and chart.id in shown and (previous is None or previous.chart.id != chart.id):
            removed.append(
                RemovedVisual(
                    line=number,
                    chart_id=chart.id,
                    reason="reappeared",
                    detail="The chart was already shown earlier in the script.",
                )
            )
        elif chart is not None:
            shown.add(chart.id)
            emphasis = line.chart_emphasis or None
            if emphasis and all(item.key != emphasis for item in chart.items):
                removed.append(
                    RemovedVisual(
                        line=number,
                        chart_id=chart.id,
                        reason="unknown_emphasis",
                        detail=f"The chart has no item '{emphasis}'.",
                    )
                )
                emphasis = None
            visual = LineVisual(chart=chart, emphasis=emphasis)
        attached.append(
            NarrationLine(
                text=line.text, target_id=line.target_id, sources=line.source_urls, visual=visual, figures=line.figures
            )
        )
    return attached, removed


def _normalize_url(url: str) -> str:
    # Search results often carry tracking params (e.g. utm_source=openai) and the model
    # may copy a URL with or without them, or with a trailing slash.
    parts = urlsplit(url.strip())
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if not k.lower().startswith("utm_")])
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), query, ""))


def _is_blocked(url: str) -> bool:
    host = urlsplit(url.strip()).hostname or ""
    return any(host == domain or host.endswith(f".{domain}") for domain in BLOCKED_SOURCE_DOMAINS)


def filter_sources(
    lines: list[NarrationLine], seen_urls: set[str]
) -> tuple[list[NarrationLine], list[RemovedSource]]:
    """Returns (filtered lines, the URLs that were removed and why).

    A URL is kept only if it came back from this run's searches and isn't on a blocked
    site. Kept URLs are replaced by the search result's own spelling of them, and
    duplicates within a line are removed.
    """
    seen = {_normalize_url(url): url for url in seen_urls}
    filtered: list[NarrationLine] = []
    removed: list[RemovedSource] = []
    for number, line in enumerate(lines, start=1):
        kept: list[str] = []
        for url in line.sources:
            match = seen.get(_normalize_url(url))
            if match is None:
                removed.append(RemovedSource(line=number, url=url, reason="unverified"))
            elif _is_blocked(match):
                removed.append(RemovedSource(line=number, url=match, reason="blocked"))
            elif match not in kept:
                kept.append(match)
        filtered.append(line.model_copy(update={"sources": kept}))
    return filtered, removed


def check_removed_lines(removed: int, total: int, max_removed_ratio: float = 0.5) -> None:
    """Rejects a script that lost most of its lines to figures that didn't check out -
    what is left is not the walkthrough the model wrote, and not worth playing."""
    if total and removed / total > max_removed_ratio:
        raise NarrationQualityError(
            f"{removed} of {total} narration lines stated figures that don't match the report."
        )


def check_quality(lines: list[NarrationLine], repair_count: int, max_repair_ratio: float = 0.5) -> None:
    """Rejects scripts that are empty or mostly pointed at ids that don't exist - at
    that point the model clearly didn't work from the real report."""
    if not lines:
        raise NarrationQualityError("Narration script is empty.")
    if repair_count / len(lines) > max_repair_ratio:
        raise NarrationQualityError(
            f"{repair_count} of {len(lines)} narration lines targeted ids that don't exist in the report."
        )
