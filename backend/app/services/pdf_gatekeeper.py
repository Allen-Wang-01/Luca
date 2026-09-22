# Cheap, local pre-flight checks to avoid spending an LLM call on an upload that's
# empty, absurdly large, or obviously not a financial report. All of this reads only
# the PDF's byte size, page count, and text layer - it never feeds text to the LLM,
# which still reads the PDF itself for the real extraction.
import io

from pypdf import PdfReader

MAX_PDF_SIZE_BYTES = 25 * 1024 * 1024  # ~25MB
MAX_PAGES = 500  # generous - well beyond even a large 10-K with all exhibits attached

_KEYWORDS = [
    "total revenue",
    "net income",
    "net loss",
    "balance sheet",
    "consolidated statements",
    "condensed consolidated",
    "cash flow",
    "gross margin",
    "operating expenses",
    "stockholders' equity",
    "shareholders' equity",
    "10-q",
    "10-k",
    "fiscal quarter",
    "fiscal year",
]

_PAGES_TO_SCAN = 10
_MIN_TEXT_LENGTH = 20  # below this, treat as "no usable text layer" (e.g. a scan)
_MIN_KEYWORD_MATCHES = 3


def check_pdf(pdf_bytes: bytes) -> str | None:
    """Returns a rejection reason if this PDF shouldn't be sent to the LLM, or None
    if it's fine to proceed. Every check here is local and free."""
    if len(pdf_bytes) == 0:
        return "The uploaded file is empty."
    if len(pdf_bytes) > MAX_PDF_SIZE_BYTES:
        return f"PDF exceeds the {MAX_PDF_SIZE_BYTES // (1024 * 1024)}MB size limit."

    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        page_count = len(reader.pages)
    except Exception:
        # pypdf can raise several different exception types on malformed input;
        # any of them means we can't proceed, so this boundary catches broadly.
        return "The file could not be read as a PDF."

    if page_count == 0:
        return "The PDF has no pages."
    if page_count > MAX_PAGES:
        return f"PDF has {page_count} pages, which exceeds the {MAX_PAGES}-page limit."

    if not _looks_like_financial_report(reader):
        return (
            "This doesn't look like a financial report. Please upload a report PDF "
            "(10-Q, 10-K, quarterly/annual report, etc.)."
        )

    return None


def _looks_like_financial_report(reader: PdfReader) -> bool:
    text = "\n".join(
        page.extract_text() or "" for page in reader.pages[:_PAGES_TO_SCAN]
    ).lower()

    if len(text.strip()) < _MIN_TEXT_LENGTH:
        return True  # no usable text layer - inconclusive, don't block

    matches = sum(1 for keyword in _KEYWORDS if keyword in text)
    return matches >= _MIN_KEYWORD_MATCHES
