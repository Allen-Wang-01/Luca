# Converts the LLM's id-free output into a real FinancialReport with deterministic,
# guaranteed-unique ids. See docs/schema.md for the id rules this implements.
import re
from datetime import datetime, timezone

from app.core.logging import get_logger
from app.models.llm_report import (
    LLMChartBlock,
    LLMFinancialReport,
    LLMParagraphBlock,
    LLMRow,
    LLMTableBlock,
)
from app.models.report import (
    Block,
    Cell,
    ChartBlock,
    FinancialReport,
    ParagraphBlock,
    ReportMeta,
    Row,
    Section,
    SumTerm,
    TableBlock,
)

logger = get_logger(__name__)

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(text: str) -> str:
    slug = _SLUG_RE.sub("_", text.lower()).strip("_")
    return slug or "block"


def _heading(group: str | None) -> str | None:
    # Shown in front of the row's own label ("Operating expenses · Other"), where the
    # colon a sub-heading usually ends with would read oddly.
    text = (group or "").strip().rstrip(":").strip()
    return text or None


def _indexes_match(rows: list[LLMRow]) -> bool:
    # Rows refer to each other by the index the model wrote on each. If any of those is
    # off, its references may point one row away from what it meant, and a wrong
    # relationship would flag correct figures - so the whole table's are left out.
    return all(row.index == position for position, row in enumerate(rows))


def _sum_terms(table_id: str, row_index: int, rows: list[LLMRow]) -> list[SumTerm]:
    """The rows this one is the total of, by row id. Empty if any reference can't be
    one: out of range, the row itself, a row without figures, or the same row twice."""
    terms = rows[row_index].sum_of or []
    indexes = [term.index for term in terms]
    usable = len(set(indexes)) == len(indexes) and all(
        0 <= index < len(rows) and index != row_index and rows[index].cells for index in indexes
    )
    if not usable:
        return []
    return [SumTerm(row_id=f"{table_id}__r{term.index}", sign=term.sign) for term in terms]


class _IdAllocator:
    def __init__(self) -> None:
        self._used: set[str] = set()

    def allocate(self, prefix: str, slug: str) -> str:
        base = f"{prefix}_{_slugify(slug)}"
        candidate = base
        suffix = 2
        while candidate in self._used:
            candidate = f"{base}_{suffix}"
            suffix += 1
        self._used.add(candidate)
        return candidate


def assign_ids(llm_report: LLMFinancialReport, source_filename: str) -> FinancialReport:
    allocator = _IdAllocator()
    slug_to_id: dict[str, str] = {}
    blocks: list[Block] = []

    for llm_block in llm_report.blocks:
        if isinstance(llm_block, LLMParagraphBlock):
            block_id = allocator.allocate("p", llm_block.slug)
            blocks.append(
                ParagraphBlock(
                    id=block_id,
                    style=llm_block.style,
                    text=llm_block.text,
                    page=llm_block.page,
                )
            )
        elif isinstance(llm_block, LLMTableBlock):
            block_id = allocator.allocate("t", llm_block.slug)
            rows: list[Row] = []
            sums_usable = _indexes_match(llm_block.rows)
            for row_index, llm_row in enumerate(llm_block.rows):
                row_id = f"{block_id}__r{row_index}"
                cells = [
                    Cell(
                        id=f"{row_id}_{llm_cell.col_id}",
                        col_id=llm_cell.col_id,
                        value=llm_cell.value,
                        raw_text=llm_cell.raw_text,
                        value_type=llm_cell.value_type,
                    )
                    for llm_cell in llm_row.cells
                ]
                rows.append(
                    Row(
                        id=row_id,
                        label=llm_row.label,
                        cells=cells,
                        # A row without figures measures nothing, whatever the model put.
                        quantity=llm_row.quantity if cells else None,
                        scale=llm_row.scale if cells else None,
                        group=_heading(llm_row.group),
                        sum_of=_sum_terms(block_id, row_index, llm_block.rows) if sums_usable and cells else [],
                    )
                )
            blocks.append(
                TableBlock(
                    id=block_id,
                    title=llm_block.title,
                    unit=llm_block.unit,
                    column_groups=llm_block.column_groups,
                    columns=llm_block.columns,
                    rows=rows,
                    confidence=llm_block.confidence,
                    page=llm_block.page,
                )
            )
        elif isinstance(llm_block, LLMChartBlock):
            block_id = allocator.allocate("c", llm_block.slug)
            blocks.append(
                ChartBlock(
                    id=block_id,
                    title=llm_block.title,
                    chart_type=llm_block.chart_type,
                    unit=llm_block.unit,
                    series=llm_block.series,
                    confidence=llm_block.confidence,
                    note=llm_block.note,
                    page=llm_block.page,
                )
            )
        else:  # pragma: no cover - exhaustive over the LLMBlock union
            raise TypeError(f"Unknown LLM block type: {llm_block!r}")

        slug_to_id[llm_block.slug] = block_id

    # Sections are only navigation, and the model can name a block in one that it never
    # wrote. Such a reference is dropped, and a section left with nothing in it with it,
    # rather than failing a parse whose content is all there.
    sections: list[Section] = []
    for llm_section in llm_report.sections:
        block_ids: list[str] = []
        for slug in llm_section.block_slugs:
            if slug in slug_to_id:
                block_ids.append(slug_to_id[slug])
            else:
                logger.warning("section_block_missing section=%s slug=%s", llm_section.slug, slug)
        if block_ids:
            sections.append(
                Section(id=allocator.allocate("sec", llm_section.slug), title=llm_section.title, block_ids=block_ids)
            )

    meta = ReportMeta(
        **llm_report.meta.model_dump(),
        source_filename=source_filename,
        parsed_at=datetime.now(timezone.utc),
    )

    return FinancialReport(meta=meta, sections=sections, blocks=blocks)
