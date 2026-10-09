# Checks the figures a narration line states against the figures it cites. The
# calculation tools keep the model's arithmetic honest, but nothing stopped it from
# saying a number that isn't the one it meant - last year's profit read out as this
# year's. So every line lists where its figures come from (`figures`, the same
# references the tools take), and this module compares:
#
# - each amount or percentage in the text must match one of the line's references,
#   within the rounding it was said with ("about $12.4 billion" for a cell of 12,387).
#   This can be checked exactly, so a line that still fails after the model has had
#   its chance to correct it is cut (`must_fix`).
# - two patterns that usually mean the right number from the wrong place: a cited cell
#   that shares neither a row nor a column with the others cited from its table, and a
#   highlighted cell the line doesn't cite. These can be wrong about a deliberate
#   comparison, so the model is asked to look again and the line stays either way.
#
# A line can also carry a calculation of its own (`calculations`): the figures and the
# operation, for a number that came to the model while writing. It is worked out here
# with the calculation tools' own code, and its result is one more thing the line's
# figures may match - so the arithmetic is still not the model's, without the turn a
# tool call would have cost.
#
# What these can't see - a sentence about one figure that names the wrong period - is
# left to narration_reviewer.py. Pure functions, no I/O.
import re
from dataclasses import dataclass

from app.models.narration import LineCalculationResult, LLMNarrationLine, ReviewFinding, ReviewRound
from app.services.narration_tools import FigureIndex, _Operand, evaluate

_SCALE_WORD_FACTORS = {"thousand": 1e3, "million": 1e6, "billion": 1e9, "trillion": 1e12}

# A number counts as a stated figure when it is marked as money, a scale or a
# percentage. Bare numbers are left alone: they are mostly dates, periods and counts
# ("the first nine months", "June 30, 2031") that cite nothing.
_FIGURE_RE = re.compile(
    r"(?P<dollar>\$\s?)?"
    r"(?P<number>\d[\d,]*(?:\.\d+)?)"
    r"(?:\s*(?P<scale>thousand|million|billion|trillion)\b|\s*(?P<percent>%|percent\b|percentage points?\b))?",
    re.IGNORECASE,
)


# How far off a figure may be said when it is rounded more loosely than to its last
# digit, as a share of the figure itself.
_LOOSE_ROUNDING = 0.025


@dataclass(frozen=True)
class SpokenFigure:
    text: str  # as written in the line, e.g. "$12.4 billion"
    value: float  # in actual units; for a percentage, the percentage itself
    # One unit of the last digit said, on the same scale as `value`.
    step: float
    # One unit of the last digit that isn't a zero: 100 million for "$300 million". A
    # round number may have been rounded that far.
    loose_step: float
    is_percent: bool


def spoken_figures(text: str) -> list[SpokenFigure]:
    figures: list[SpokenFigure] = []
    for match in _FIGURE_RE.finditer(text):
        is_percent = match["percent"] is not None
        if not (match["dollar"] or match["scale"] or is_percent):
            continue
        number = match["number"].rstrip(",")
        factor = 1.0 if is_percent or not match["scale"] else _SCALE_WORD_FACTORS[match["scale"].lower()]
        decimals = len(number.partition(".")[2])
        digits = number.replace(",", "").replace(".", "")
        trailing_zeros = len(digits) - len(digits.rstrip("0")) if digits.strip("0") else 0
        figures.append(
            SpokenFigure(
                text=" ".join(match.group().split()).rstrip(","),
                value=float(number.replace(",", "")) * factor,
                step=10**-decimals * factor,
                loose_step=10.0 ** (trailing_zeros - decimals) * factor,
                is_percent=is_percent,
            )
        )
    return figures


def _matches(spoken: SpokenFigure, operand: _Operand) -> bool:
    if spoken.is_percent != operand.is_percent:
        return False
    # Signs are dropped: an outflow printed as (120) is said as "spent $120 million".
    actual = abs(operand.value if operand.is_percent else operand.absolute)
    gap = abs(actual - spoken.value)
    # Rounded to the last digit said - or, since speech rounds loosely ("nearly $30
    # billion" for 29.4), within a unit of the last digit that isn't a zero, as long as
    # that is a small share of the figure. The share is what keeps "3%" from passing
    # for 2%.
    if gap <= spoken.step * (0.5 + 1e-9):
        return True
    return gap <= spoken.loose_step and gap <= _LOOSE_ROUNDING * actual


def _finding(number: int, line: LLMNarrationLine, check: str, detail: str, must_fix: bool) -> ReviewFinding:
    return ReviewFinding(line=number, text=line.text, check=check, detail=detail, must_fix=must_fix)


@dataclass(frozen=True)
class LineFigures:
    # Everything the line's stated figures may match: what it cites, and the results of
    # the calculations it carries.
    operands: list[_Operand]
    # Formulas of the calculations it carries, as worked out.
    formulas: list[str]
    # (check, detail) for each reference that names nothing and each calculation that
    # couldn't be done.
    errors: list[tuple[str, str]]


def resolve_figures(line: LLMNarrationLine, index: FigureIndex) -> LineFigures:
    operands: list[_Operand] = []
    formulas: list[str] = []
    errors: list[tuple[str, str]] = []
    for reference in line.figures:
        operand, error = index.resolve(reference.model_dump())
        if operand is not None:
            operands.append(operand)
        else:
            errors.append(("unknown_reference", error))
    for calculation in line.calculations:
        operand, output = evaluate(index, calculation.operation, [term.model_dump() for term in calculation.terms])
        if operand is not None:
            operands.append(operand)
            formulas.append(output["formula"])
        else:
            errors.append(("calculation_error", f"The line's `{calculation.operation}` calculation failed: {output['error']}"))
    return LineFigures(operands=operands, formulas=formulas, errors=errors)


def _isolated_cells(operands: list[_Operand], index: FigureIndex) -> list[_Operand]:
    """Cited cells that share neither a row nor a column with any other cell the line
    cites from the same table. Comparisons run along a row (one metric, two periods) or
    down a column (two metrics, one period); a cell off on a diagonal is the shape of
    this year's figure for one thing set against last year's for another."""
    cells = [(operand, index.cell_positions[operand.id]) for operand in operands if operand.id in index.cell_positions]
    isolated: list[_Operand] = []
    for operand, (table, row, column) in cells:
        others = [position for other, position in cells if other.id != operand.id and position[0] == table]
        if others and not any(row == other_row or column == other_column for _, other_row, other_column in others):
            isolated.append(operand)
    return isolated


def check_line(number: int, line: LLMNarrationLine, index: FigureIndex) -> tuple[list[ReviewFinding], int, list[str]]:
    """Returns (findings, how many of the line's stated figures matched a reference,
    the formulas of the calculations the line carries)."""
    findings: list[ReviewFinding] = []
    resolved = resolve_figures(line, index)
    operands = resolved.operands
    for check, detail in resolved.errors:
        findings.append(_finding(number, line, check, detail, must_fix=True))

    confirmed = 0
    for spoken in spoken_figures(line.text):
        if any(_matches(spoken, operand) for operand in operands):
            confirmed += 1
        elif not line.source_urls:
            # A line that cites a web page may be quoting a figure from it, which
            # nothing here can check.
            cited = ", ".join(f"{operand.label} ({operand.raw_text})" for operand in operands) or "nothing"
            detail = f"'{spoken.text}' matches none of the figures the line cites: {cited}."
            findings.append(_finding(number, line, "figure_mismatch", detail, must_fix=True))

    isolated = _isolated_cells(operands, index)
    if isolated:
        names = " and ".join(f"'{operand.label}'" for operand in isolated)
        detail = (
            f"{names} {'shares' if len(isolated) == 1 else 'share'} neither a row nor a period with the other "
            "figures this line cites from the same table. Check each is the item and the period the sentence means."
        )
        findings.append(_finding(number, line, "isolated_cell", detail, must_fix=False))

    target = index.cell_positions.get(line.target_id)
    cited_ids = {operand.id for operand in operands}
    same_table = [o for o in operands if o.id in index.cell_positions and index.cell_positions[o.id][0] == target[0]] if target else []
    if same_table and line.target_id not in cited_ids:
        detail = (
            f"The line highlights the cell '{line.target_id}' but cites other cells of that table "
            f"({', '.join(operand.label for operand in same_table)}). Highlight the figure the line is about, "
            "or cite the highlighted one if the line states it."
        )
        findings.append(_finding(number, line, "target_not_cited", detail, must_fix=False))
    return findings, confirmed, resolved.formulas


def check_script(lines: list[LLMNarrationLine], index: FigureIndex) -> ReviewRound:
    """Checks every line; lines are numbered from 1."""
    review_round = ReviewRound(lines=len(lines), figures_confirmed=0, findings=[])
    for number, line in enumerate(lines, start=1):
        findings, confirmed, formulas = check_line(number, line, index)
        review_round.findings.extend(findings)
        review_round.figures_confirmed += confirmed
        review_round.calculations.extend(LineCalculationResult(line=number, formula=formula) for formula in formulas)
    return review_round
