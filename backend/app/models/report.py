from datetime import datetime
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


UnitScale = Literal["actual", "thousands", "millions", "billions"]


class ReportMeta(BaseModel):
    company_name: str
    ticker: str | None = None
    report_type: str
    fiscal_period: str
    currency: str
    unit_scale: UnitScale
    source_filename: str
    parsed_at: datetime


class Flag(BaseModel):
    severity: Literal["warning", "error"]
    code: str
    message: str


class ParagraphBlock(BaseModel):
    id: str
    type: Literal["paragraph"] = "paragraph"
    style: Literal["heading", "body", "note", "list_item"]
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


# What a row's figures measure. Figures of different kinds can be divided by one
# another but not added, subtracted or drawn on one axis.
Quantity = Literal["money", "per_share", "share_count", "percent", "other"]


class Row(BaseModel):
    id: str
    label: str
    cells: list[Cell]
    flags: list[Flag] = Field(default_factory=list)
    # The three below are filled in by the parser and missing from reports parsed
    # before they existed; None falls back to guessing from the row label and the
    # report's unit scale.
    quantity: Quantity | None = None
    # The scale this row's figures are printed in, which need not be the report's (a
    # share count in thousands in a statement in millions).
    scale: UnitScale | None = None
    # The sub-heading the row sits under, for telling apart rows that share a label.
    group: str | None = None


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
