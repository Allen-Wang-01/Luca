import json
import queue
import threading
from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.core.logging import get_logger
from app.models.narration import NarrationRequest, NarrationResponse
from app.models.report import FinancialReport
from app.services import id_assigner, llm_client, narration_agent, pdf_gatekeeper, report_validator
from app.services.narration_validator import NarrationQualityError

router = APIRouter(prefix="/api/reports")

logger = get_logger(__name__)

# A model call can run for half a minute without anything to report. A comment line this
# often keeps proxies from closing a stream they take to be idle.
STREAM_HEARTBEAT_SECONDS = 15


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


# The same run as /narration, reported while it happens: a server-sent event stream of
# the agent's events (see narration_agent.EventHandler), ending with one `result` event
# that carries what /narration would have returned, or one `error` event. The status is
# already sent by the time a run fails, so a failure is an event rather than a 502.
@router.post("/narration/stream")
def stream_narration(request: NarrationRequest) -> StreamingResponse:
    if not request.report.blocks:
        raise HTTPException(status_code=422, detail="Report has no content to narrate.")

    events: queue.Queue[dict[str, Any] | None] = queue.Queue()

    def run() -> None:
        try:
            lines, trace = narration_agent.generate_narration(request.report, on_event=events.put)
            narration = NarrationResponse(lines=lines, trace=trace)
            events.put({"type": "result", "narration": narration.model_dump(mode="json")})
        except NarrationQualityError as exc:
            events.put({"type": "error", "detail": f"Narration generation failed: {exc}"})
        except Exception:
            logger.exception("narration_stream_failed")
            events.put({"type": "error", "detail": "Narration generation failed."})
        finally:
            events.put(None)

    def body() -> Iterator[str]:
        # The run is on its own thread so this one is free to send heartbeats while a
        # model call is out. It runs to the end even if the listener goes away.
        threading.Thread(target=run, daemon=True).start()
        while True:
            try:
                event = events.get(timeout=STREAM_HEARTBEAT_SECONDS)
            except queue.Empty:
                yield ": keepalive\n\n"
                continue
            if event is None:
                return
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        body(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
