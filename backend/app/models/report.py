from datetime import datetime
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


class ReportMeta(BaseModel):
    company_name: str
    ticker: str | None = None
    report_type: str
    fiscal_period: str
    currency: str
    unit_scale: Literal["actual", "thousands", "millions", "billions"]
    source_filename: str
    parsed_at: datetime


class Flag(BaseModel):
    severity: Literal["warning", "error"]
    code: str
    message: str


class ParagraphBlock(BaseModel):
    id: str
    type: Literal["paragraph"] = "paragraph"
    style: Literal["heading", "body", "note"]
    text: str
    page: int | None = None


class ColumnGroup(BaseModel):
    label: str
    col_ids: list[str]


class Column(BaseModel):
    id: str
    label: str


class Cell(BaseModel):
    id: str
    col_id: str
    value: float | None
    raw_text: str
    value_type: Literal["number", "percent", "currency", "text"]


class Row(BaseModel):
    id: str
    label: str
    cells: list[Cell]
    flags: list[Flag] = Field(default_factory=list)


class TableBlock(BaseModel):
    id: str
    type: Literal["table"] = "table"
    title: str
    unit: str | None = None
    column_groups: list[ColumnGroup] = Field(default_factory=list)
    columns: list[Column]
    rows: list[Row]
    confidence: Literal["high", "low"] | None = None
    flags: list[Flag] = Field(default_factory=list)
    page: int | None = None


class ChartDataPoint(BaseModel):
    label: str
    value: float


class ChartSeries(BaseModel):
    name: str
    data: list[ChartDataPoint]


class ChartBlock(BaseModel):
    id: str
    type: Literal["chart"] = "chart"
    title: str
    chart_type: Literal["bar", "line", "pie", "stacked_bar"]
    unit: str | None = None
    series: list[ChartSeries]
    confidence: Literal["high", "low"] | None = None
    note: str | None = None
    page: int | None = None


Block = Annotated[Union[ParagraphBlock, TableBlock, ChartBlock], Field(discriminator="type")]


class Section(BaseModel):
    id: str
    title: str
    block_ids: list[str]


class FinancialReport(BaseModel):
    meta: ReportMeta
    sections: list[Section]
    blocks: list[Block]
