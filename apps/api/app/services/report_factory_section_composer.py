from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.models.core import BrandKit, CanonicalFact, CompanyProfile, ReportRun


DEFAULT_ASSUMPTIONS = [
    "AI gorseller yalnizca dekoratif veya konsept kullanim icindir; performans iddiasi tasimaz.",
    "Canli ERP verisi bulunmayan alanlarda proje bootstrap profili ve secili connector scope kullanilmistir.",
    "Anlati yalnizca canonical fact, company profile ve PASS claim havuzundan turetilmistir.",
]


@dataclass(frozen=True)
class ComposedReportSections:
    metric_bucket: dict[str, list[CanonicalFact]]
    section_payloads: list[dict[str, Any]]
    claim_domains: dict[str, list[str]]
    citation_index: list[dict[str, Any]]
    calculations: list[dict[str, Any]]
    assumptions: list[str]


def ensure_snapshot_rows(*, db: Session, report_run: ReportRun, facts: list[CanonicalFact]) -> None:
    from app.services import report_factory as legacy_report_factory

    legacy_report_factory._ensure_snapshot_rows(db=db, report_run=report_run, facts=facts)


def compose_report_sections(
    *,
    db: Session,
    report_run: ReportRun,
    company_profile: CompanyProfile,
    brand: BrandKit,
    blueprint_sections: list[dict[str, Any]],
    facts: list[CanonicalFact],
) -> ComposedReportSections:
    from app.services import report_factory as legacy_report_factory

    metric_bucket = legacy_report_factory._metric_bucket(facts)
    claim_domains, citation_index, calculations = legacy_report_factory._build_claim_domains(
        db=db,
        report_run_id=report_run.id,
    )
    section_payloads = [
        legacy_report_factory._build_section_payload(
            company_profile=company_profile,
            brand=brand,
            section_definition=section_definition,
            metric_bucket=metric_bucket,
            claim_domains=claim_domains,
        )
        for section_definition in blueprint_sections
    ]
    return ComposedReportSections(
        metric_bucket=metric_bucket,
        section_payloads=section_payloads,
        claim_domains=claim_domains,
        citation_index=citation_index,
        calculations=calculations,
        assumptions=list(DEFAULT_ASSUMPTIONS),
    )
