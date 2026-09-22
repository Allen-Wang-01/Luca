from fastapi import APIRouter, HTTPException, UploadFile

from app.models.report import FinancialReport
from app.services import id_assigner, llm_client, pdf_gatekeeper, report_validator

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
