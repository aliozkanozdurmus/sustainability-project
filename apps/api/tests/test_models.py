# Bu test dosyasi, models davranisini dogrular.

from app.db.base import Base
import app.models  # noqa: F401


def test_core_table_registry_contains_expected_entities() -> None:
    expected_tables = {
        "tenants",
        "users",
        "memberships",
        "projects",
        "reporting_framework_versions",
        "source_documents",
        "extraction_records",
        "chunks",
        "embeddings",
        "retrieval_runs",
        "report_runs",
        "report_sections",
        "claims",
        "claim_citations",
        "calculation_runs",
        "verification_results",
        "audit_events",
    }
    assert expected_tables.issubset(set(Base.metadata.tables.keys()))

