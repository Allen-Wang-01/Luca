from fastapi import APIRouter, HTTPException, UploadFile

from app.models.narration import NarrationRequest, NarrationResponse
from app.models.report import FinancialReport
from app.services import id_assigner, llm_client, narration_agent, pdf_gatekeeper, report_validator
from app.services.narration_validator import NarrationQualityError

router = APIRouter(prefix="/api/reports")


@router.post("/parse", response_model=FinancialReport)
async def parse_report(file: UploadFile) -> FinancialReport:
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="File must be a PDF.")

    pdf_bytes = await file.read()
    rejection_reason = pdf_gatekeeper.check_pdf(pdf_bytes)
    if rejection_reason:
        raise HTTPException(status_code=422, detail=rejection_reason)

    llm_output = llm_client.parse_report(pdf_bytes, filename=file.filename or "report.pdf")
    report = id_assigner.assign_ids(llm_output, source_filename=file.filename or "report.pdf")
    report_validator.validate(report)
    return report


# Separate from /parse (rather than chained onto it) so the report can render as soon
# as it's parsed, and narration can be retried on its own without re-parsing the PDF.
# The client sends the parsed report back; nothing is stored here.
@router.post("/narration", response_model=NarrationResponse)
def generate_narration(request: NarrationRequest) -> NarrationResponse:
    if not request.report.blocks:
        raise HTTPException(status_code=422, detail="Report has no content to narrate.")

    try:
        lines, trace = narration_agent.generate_narration(request.report)
    except NarrationQualityError as exc:
        raise HTTPException(status_code=502, detail=f"Narration generation failed: {exc}") from exc
    return NarrationResponse(lines=lines, trace=trace)
