import io

from reportlab.pdfgen import canvas

from app.services import pdf_gatekeeper
from app.services.pdf_gatekeeper import check_pdf


def _make_pdf(lines: list[str]) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    y = 800
    for line in lines:
        pdf.drawString(72, y, line)
        y -= 20
    pdf.save()
    return buffer.getvalue()


def _blank_pdf(page_count: int = 1) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    for _ in range(page_count):
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def test_accepts_a_pdf_with_financial_keywords():
    pdf_bytes = _make_pdf(
        [
            "CONDENSED CONSOLIDATED STATEMENTS OF INCOME",
            "Total revenue increased year over year.",
            "Net income and gross margin both improved.",
            "See the consolidated balance sheet for details.",
        ]
    )

    assert check_pdf(pdf_bytes) is None


def test_rejects_a_pdf_with_no_financial_content():
    pdf_bytes = _make_pdf(
        [
            "Grocery list",
            "Milk, eggs, bread, and coffee.",
            "Remember to water the plants.",
        ]
    )

    assert check_pdf(pdf_bytes) is not None


def test_passes_a_pdf_with_no_extractable_text():
    # A blank page (e.g. a scan with no OCR text layer) has no signal to reject on.
    assert check_pdf(_blank_pdf(page_count=1)) is None


def test_rejects_empty_file():
    reason = check_pdf(b"")
    assert reason is not None
    assert "empty" in reason.lower()


def test_rejects_file_too_large_to_be_a_pdf(monkeypatch):
    monkeypatch.setattr(pdf_gatekeeper, "MAX_PDF_SIZE_BYTES", 10)

    reason = check_pdf(b"x" * 100)

    assert reason is not None
    assert "size limit" in reason.lower()


def test_rejects_corrupt_pdf():
    reason = check_pdf(b"this is not a valid pdf file")

    assert reason is not None
    assert "could not be read" in reason.lower()


def test_rejects_pdf_with_too_many_pages(monkeypatch):
    monkeypatch.setattr(pdf_gatekeeper, "MAX_PAGES", 2)

    reason = check_pdf(_blank_pdf(page_count=3))

    assert reason is not None
    assert "page" in reason.lower()
