# Makes sure every narration line's target_id exists in the report, so the frontend
# sync engine always has something real to scroll to and highlight. The model is given
# the valid ids, but nothing forces it to use them exactly - a slightly wrong cell id
# (e.g. a misspelled col_id) is common and mostly recoverable. Pure function, no I/O.
import re

from app.models.narration import NarrationLine

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
        repaired.append(NarrationLine(text=text, target_id=target))
    return repaired, repair_count


def check_quality(lines: list[NarrationLine], repair_count: int, max_repair_ratio: float = 0.5) -> None:
    """Rejects scripts that are empty or mostly pointed at ids that don't exist - at
    that point the model clearly didn't work from the real report."""
    if not lines:
        raise NarrationQualityError("Narration script is empty.")
    if repair_count / len(lines) > max_repair_ratio:
        raise NarrationQualityError(
            f"{repair_count} of {len(lines)} narration lines targeted ids that don't exist in the report."
        )
