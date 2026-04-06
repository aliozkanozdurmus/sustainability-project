from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.db.session import SessionLocal
from app.models.core import ReportRun
from app.services.report_factory import REPORT_PDF_ARTIFACT_TYPE, ensure_report_package, list_run_artifacts
from app.services.report_pdf import download_report_artifact_bytes


def main() -> int:
    parser = argparse.ArgumentParser(description="Export a published or completed run to PDF.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--output",
        default=str(REPO_ROOT / "output" / "pdf" / "demo-sustainability-report.pdf"),
    )
    parser.add_argument("--desktop-copy", default=None)
    args = parser.parse_args()

    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with SessionLocal() as db:
        report_run = db.get(ReportRun, args.run_id)
        if report_run is None:
            raise SystemExit(f"Run not found: {args.run_id}")
        artifacts = list_run_artifacts(db=db, report_run_id=report_run.id)
        report_pdf_artifact = next(
            (
                artifact
                for artifact in artifacts
                if artifact.artifact_type == REPORT_PDF_ARTIFACT_TYPE
            ),
            None,
        )
        if report_pdf_artifact is None:
            package_result = ensure_report_package(db=db, report_run=report_run)
            report_pdf_artifact = next(
                (
                    artifact
                    for artifact in package_result.artifacts
                    if artifact.artifact_type == REPORT_PDF_ARTIFACT_TYPE
                ),
                None,
            )
            db.commit()
        if report_pdf_artifact is None:
            raise SystemExit(f"Report package did not produce a PDF artifact for run: {args.run_id}")
        report_pdf_bytes = download_report_artifact_bytes(report_pdf_artifact)

    output_path.write_bytes(report_pdf_bytes)

    if args.desktop_copy:
        desktop_path = Path(args.desktop_copy).resolve()
        desktop_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(output_path, desktop_path)

    print(
        {
            "run_id": args.run_id,
            "output": str(output_path),
            "desktop_copy": str(Path(args.desktop_copy).resolve()) if args.desktop_copy else None,
            "filename": report_pdf_artifact.filename,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
