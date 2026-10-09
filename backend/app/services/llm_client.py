# Wraps the OpenAI Responses API for financial report extraction. Logs token usage
# and cost on every call - see app/core/pricing.py for the pricing table.
import base64
import time

from openai import OpenAI

from app.config import settings
from app.core.logging import get_logger
from app.core.pricing import calculate_cost
from app.models.llm_report import LLMFinancialReport

logger = get_logger(__name__)

MODEL = "gpt-5.6-luna"

client = OpenAI(
    # Falls back to the OPENAI_API_KEY env var if not set here.
    api_key=settings.openai_api_key,
    base_url=settings.openai_base_url,
)

INSTRUCTIONS = """You are a financial report parser. Read the attached PDF and extract \
its content as structured data matching the given schema.

Rules:
- Extract paragraphs, tables, and charts as separate blocks, in document order.
- Paragraph `text` must be extracted VERBATIM - the exact original wording, not a \
paraphrase, summary, or rewording. Do not rephrase sentences, drop words like \
"respectively", or restructure sentence order, even if it reads awkwardly. The only \
exception is fixing obvious OCR artifacts (e.g. a broken mid-word line break).
- If the source presents a bulleted or numbered list, extract EACH item as its own \
separate paragraph block with style="list_item" - do not merge list items into one \
paragraph. Each item's text should be verbatim, without the bullet marker or number \
itself (the style field already conveys that it's a list item).
- For each block, propose a short, human-readable `slug` (e.g. "income_statement"); \
it does not need to be globally unique, just descriptive.
- For tables, extract every row and every numeric column exactly as printed. Put the \
row's original numeric text in `raw_text` and the parsed numeric value (no commas, no \
currency symbols, negative for parentheses) in `value`.
- Every table must carry its complete header: all of its columns and, where columns \
sit under shared headers (e.g. two period headers, each over a current and a \
prior-year column), every one of those in `column_groups`. This also holds when the \
source prints the header only once for several tables - a statement followed by \
breakdowns set under the same column headings, or a table continued on the next \
page: repeat the full header, groups included, on each of them. Without the groups, \
columns that share a label cannot be told apart.
- For every table row with figures, set `quantity` and `scale` from what the row \
measures and the table's unit note, and set `group` to the sub-heading the row is \
listed under, if any. A statement often mixes kinds and scales (amounts in millions \
next to per-share amounts and share counts), and repeats a label under different \
sub-headings, so these are what tell such rows apart later.
- Number every table row with its `index`, and for each total or subtotal list in \
`sum_of` the rows that add up to it. These are used to check the extracted figures \
against each other, so only state a relationship the statement itself shows.
- Prefer expressing chart data as structured series (label/value pairs) rather than \
describing the chart in prose.
- Set `confidence` to "low" on any table or chart you were not confident reading \
(e.g. small print, ambiguous figures).
- Group related blocks (e.g. a heading, its table, and any commentary) into the same \
section.
"""


def parse_report(pdf_bytes: bytes, filename: str) -> LLMFinancialReport:
    encoded = base64.b64encode(pdf_bytes).decode("ascii")

    start = time.monotonic()
    response = client.responses.parse(
        model=MODEL,
        instructions=INSTRUCTIONS,
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_file",
                        "filename": filename,
                        "file_data": f"data:application/pdf;base64,{encoded}",
                    },
                    {
                        "type": "input_text",
                        "text": "Extract this financial report into the given schema.",
                    },
                ],
            }
        ],
        text_format=LLMFinancialReport,
    )
    duration = time.monotonic() - start

    usage = response.usage
    cost = calculate_cost(MODEL, usage.input_tokens, usage.output_tokens)
    logger.info(
        "llm_call model=%s input_tokens=%d output_tokens=%d cost_usd=%.6f duration_s=%.2f filename=%s",
        MODEL,
        usage.input_tokens,
        usage.output_tokens,
        cost,
        duration,
        filename,
    )

    return response.output_parsed
