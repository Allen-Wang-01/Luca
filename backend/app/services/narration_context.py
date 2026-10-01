# Renders a FinancialReport into the compact, id-annotated text the narration model
# reads. Raw JSON would work too, but it spends most of its tokens on repeated keys and
# per-cell ids; this format lists each row once with its id and states the cell id rule
# instead, which keeps the prompt small while still letting the model point at a single
# cell. Pure function, no I/O.
from app.models.report import ChartBlock, FinancialReport, ParagraphBlock, Row, TableBlock


def collect_target_ids(report: FinancialReport) -> set[str]:
    ids: set[str] = set()
    for block in report.blocks:
        ids.add(block.id)
        if isinstance(block, TableBlock):
            for row in block.rows:
                ids.add(row.id)
                ids.update(cell.id for cell in row.cells)
    return ids


def render_report_for_prompt(report: FinancialReport) -> str:
    meta = report.meta
    lines = [
        f"Company: {meta.company_name}" + (f" ({meta.ticker})" if meta.ticker else ""),
        f"Report: {meta.report_type}, {meta.fiscal_period}",
        f"Currency: {meta.currency}, figures in {meta.unit_scale} unless a table says otherwise",
        "",
    ]

    section_by_block_id: dict[str, str] = {}
    for section in report.sections:
        for block_id in section.block_ids:
            section_by_block_id.setdefault(block_id, section.title)

    current_section: str | None = None
    for block in report.blocks:
        section = section_by_block_id.get(block.id)
        if section and section != current_section:
            lines.append(f"## Section: {section}")
            current_section = section

        if isinstance(block, ParagraphBlock):
            lines.append(f"[{block.id}] ({block.style}) {block.text}")
        elif isinstance(block, TableBlock):
            lines.extend(_render_table(block))
        elif isinstance(block, ChartBlock):
            lines.extend(_render_chart(block))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _render_table(table: TableBlock) -> list[str]:
    header = f'[{table.id}] TABLE "{table.title}"'
    if table.unit:
        header += f" (unit: {table.unit})"
    if table.confidence == "low":
        header += " [LOW EXTRACTION CONFIDENCE]"
    lines = [header]
    for flag in table.flags:
        lines.append(f"  ! table flag: {flag.message}")

    columns = " | ".join(f'{c.id}="{c.label}"' for c in table.columns)
    lines.append(f"  columns: {columns}")
    for group in table.column_groups:
        lines.append(f'  column group "{group.label}": {", ".join(group.col_ids)}')

    for row in table.rows:
        lines.append(f"  {_render_row(row)}")
    return lines


def _render_row(row: Row) -> str:
    values = " | ".join(f"{cell.col_id}={cell.raw_text or '-'}" for cell in row.cells)
    text = f"[{row.id}] {row.label}: {values}" if values else f"[{row.id}] {row.label}"
    for flag in row.flags:
        text += f"  ! FLAG: {flag.message}"
    return text


def _render_chart(chart: ChartBlock) -> list[str]:
    header = f'[{chart.id}] CHART ({chart.chart_type}) "{chart.title}"'
    if chart.unit:
        header += f" (unit: {chart.unit})"
    if chart.confidence == "low":
        header += " [LOW EXTRACTION CONFIDENCE]"
    lines = [header]
    for series in chart.series:
        points = ", ".join(f"{p.label}={p.value:g}" for p in series.data)
        lines.append(f"  series {series.name}: {points}")
    if chart.note:
        lines.append(f"  note: {chart.note}")
    return lines
