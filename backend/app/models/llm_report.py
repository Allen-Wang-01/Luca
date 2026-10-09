# What the LLM actually returns: same shape as FinancialReport (see report.py and
# docs/schema.md), but blocks/sections carry a `slug` instead of a final `id`, and
# rows/cells carry no id at all. The LLM is not trusted to generate globally-unique
# ids — app/services/id_assigner.py converts this into a real FinancialReport.
from typing import Literal, Union

from pydantic import BaseModel, Field

from app.models.report import ChartSeries, Column, ColumnGroup, Quantity, UnitScale


class LLMReportMeta(BaseModel):
    # Same as ReportMeta minus source_filename/parsed_at, which the backend fills in
    # itself rather than trusting the LLM to know or invent them.
    company_name: str
    ticker: str | None = None
    report_type: str
    fiscal_period: str
    currency: str
    unit_scale: UnitScale


class LLMParagraphBlock(BaseModel):
    slug: str
    type: Literal["paragraph"] = "paragraph"
    style: Literal["heading", "body", "note", "list_item"]
    text: str
    page: int | None = None


class LLMCell(BaseModel):
    col_id: str
    value: float | None
    raw_text: str
    value_type: Literal["number", "percent", "currency", "text"]


class LLMRow(BaseModel):
    label: str
    cells: list[LLMCell]
    quantity: Quantity | None = Field(
        default=None,
        description=(
            "What the row's figures measure: 'money' for an amount of currency, 'per_share' "
            "for an amount per share, 'share_count' for a number of shares, 'percent' for a "
            "rate or margin, 'other' for any other count or measure (employees, stores, "
            "days). null for a row with no figures."
        ),
    )
    scale: UnitScale | None = Field(
        default=None,
        description=(
            "The scale this row's figures are printed in, read from the table's unit note: "
            "'millions' if 1,250 means 1,250 million. Rows the note excepts have their own: "
            "under 'in millions, except share data in thousands', a share-count row is "
            "'thousands' and a per-share row is 'actual'. null for a percent row or a row "
            "with no figures."
        ),
    )
    group: str | None = Field(
        default=None,
        description=(
            "The label of the sub-heading row this row is listed under, exactly as that "
            "heading is written (e.g. 'Operating expenses:' for a row indented beneath it). "
            "null for a row that is not under a sub-heading, including the sub-heading "
            "rows themselves and totals printed back at the outer level."
        ),
    )


class LLMTableBlock(BaseModel):
    slug: str
    type: Literal["table"] = "table"
    title: str
    unit: str | None = None
    column_groups: list[ColumnGroup] = Field(default_factory=list)
    columns: list[Column]
    rows: list[LLMRow]
    confidence: Literal["high", "low"] | None = None
    page: int | None = None


class LLMChartBlock(BaseModel):
    slug: str
    type: Literal["chart"] = "chart"
    title: str
    chart_type: Literal["bar", "line", "pie", "stacked_bar"]
    unit: str | None = None
    series: list[ChartSeries]
    confidence: Literal["high", "low"] | None = None
    note: str | None = None
    page: int | None = None


# No discriminator here (unlike Block in report.py): pydantic renders a discriminated
# union as JSON Schema's "oneOf", which OpenAI's structured-output schema validator
# rejects ("'oneOf' is not permitted"). A plain Union renders as "anyOf", which it
# accepts - validation still works fine, each variant has a distinct `type` literal.
LLMBlock = Union[LLMParagraphBlock, LLMTableBlock, LLMChartBlock]


class LLMSection(BaseModel):
    slug: str
    title: str
    block_slugs: list[str]


class LLMFinancialReport(BaseModel):
    meta: LLMReportMeta
    sections: list[LLMSection]
    blocks: list[LLMBlock]
