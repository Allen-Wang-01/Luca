# Manual end-to-end run against the real API. Costs real money per run, so this is
# not part of the automated test suite - run it by hand to sanity-check extraction
# quality against a real filing.
#
# Usage: python scripts/parse_sample.py path/to/report.pdf
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import id_assigner, llm_client, pdf_gatekeeper, report_validator


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python scripts/parse_sample.py path/to/report.pdf", file=sys.stderr)
        sys.exit(1)

    pdf_path = Path(sys.argv[1])
    pdf_bytes = pdf_path.read_bytes()

    rejection_reason = pdf_gatekeeper.check_pdf(pdf_bytes)
    if rejection_reason:
        print(f"Gatekeeper: {rejection_reason}", file=sys.stderr)
        sys.exit(1)

    llm_output = llm_client.parse_report(pdf_bytes, filename=pdf_path.name)
    report = id_assigner.assign_ids(llm_output, source_filename=pdf_path.name)
    report_validator.validate(report)

    print(json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
