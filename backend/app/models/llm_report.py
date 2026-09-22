# What the LLM actually returns: same shape as FinancialReport (see report.py and
# docs/schema.md), but blocks/sections carry a `slug` instead of a final `id`, and
# rows/cells carry no id at all. The LLM is not trusted to generate globally-unique
# ids — app/services/id_assigner.py converts this into a real FinancialReport.
from typing import Literal, Union

from pydantic import BaseModel, Field

from app.models.report import ChartSeries, Column, ColumnGroup


class LLMReportMeta(BaseModel):
    # Same as ReportMeta minus source_filename/parsed_at, which the backend fills in
    # itself rather than trusting the LLM to know or invent them.
    company_name: str
    ticker: str | None = None
    report_type: str
    fiscal_period: str
    currency: str
    unit_scale: Literal["actual", "thousands", "millions", "billions"]


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
