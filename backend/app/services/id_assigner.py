# Converts the LLM's id-free output into a real FinancialReport with deterministic,
# guaranteed-unique ids. See docs/schema.md for the id rules this implements.
import re
from datetime import datetime, timezone

from app.models.llm_report import (
    LLMChartBlock,
    LLMFinancialReport,
    LLMParagraphBlock,
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
    TableBlock,
)

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(text: str) -> str:
    slug = _SLUG_RE.sub("_", text.lower()).strip("_")
    return slug or "block"


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
                rows.append(Row(id=row_id, label=llm_row.label, cells=cells))
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

    sections = [
        Section(
            id=allocator.allocate("sec", llm_section.slug),
            title=llm_section.title,
            block_ids=[slug_to_id[slug] for slug in llm_section.block_slugs],
        )
        for llm_section in llm_report.sections
    ]

    meta = ReportMeta(
        **llm_report.meta.model_dump(),
        source_filename=source_filename,
        parsed_at=datetime.now(timezone.utc),
    )

    return FinancialReport(meta=meta, sections=sections, blocks=blocks)
