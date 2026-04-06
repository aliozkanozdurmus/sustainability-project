from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from uuid import uuid4


REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

# Compose-friendly defaults so the script works inside `docker compose exec api ...`
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("ALLOW_LOCAL_DEV_DATABASE", "true")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@postgres:5432/sustainability",
)
os.environ.setdefault("AZURE_STORAGE_USE_LOCAL", "true")
os.environ.setdefault("AZURE_AI_SEARCH_USE_LOCAL", "true")
os.environ.setdefault("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-5.2")
os.environ.setdefault("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-large")

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.core import Project, Tenant
from seed_demo_evidence import seed_demo_evidence


def _slugify(value: str) -> str:
    return "-".join(part for part in "".join(
        ch.lower() if ch.isalnum() else " " for ch in value.strip()
    ).split() if part)


def _codeify(value: str) -> str:
    letters = [ch.upper() if ch.isalnum() else "-" for ch in value.strip()]
    normalized = "".join(letters).strip("-")
    while "--" in normalized:
        normalized = normalized.replace("--", "-")
    return normalized or "DEMO"


def _default_suffix() -> str:
    return uuid4().hex[:8]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create/reuse a demo workspace and seed deterministic ESG evidence."
    )
    parser.add_argument("--tenant-name", default=None)
    parser.add_argument("--tenant-slug", default=None)
    parser.add_argument("--project-name", default=None)
    parser.add_argument("--project-code", default=None)
    parser.add_argument("--reporting-currency", default="TRY")
    args = parser.parse_args()

    suffix = _default_suffix()
    tenant_name = args.tenant_name or f"Playwright Demo Tenant {suffix}"
    tenant_slug = args.tenant_slug or f"{_slugify(tenant_name)}-{suffix}"
    project_name = args.project_name or f"Publish PDF Demo {suffix}"
    project_code = args.project_code or f"{_codeify(project_name)}-{suffix}".upper()
    reporting_currency = args.reporting_currency.strip().upper() or "TRY"

    with SessionLocal() as db:
        tenant = db.scalar(select(Tenant).where(Tenant.slug == tenant_slug))
        tenant_created = False
        if tenant is None:
            tenant = Tenant(name=tenant_name, slug=tenant_slug, status="active")
            db.add(tenant)
            db.flush()
            tenant_created = True

        project = db.scalar(
            select(Project).where(
                Project.tenant_id == tenant.id,
                Project.code == project_code,
            )
        )
        project_created = False
        if project is None:
            project = Project(
                tenant_id=tenant.id,
                name=project_name,
                code=project_code,
                reporting_currency=reporting_currency,
                status="active",
            )
            db.add(project)
            db.flush()
            project_created = True

        db.commit()
        db.refresh(tenant)
        db.refresh(project)

    seed_info = seed_demo_evidence(tenant_id=tenant.id, project_id=project.id)

    print(
        json.dumps(
            {
                "tenant_id": tenant.id,
                "tenant_slug": tenant.slug,
                "tenant_name": tenant.name,
                "tenant_created": tenant_created,
                "project_id": project.id,
                "project_code": project.code,
                "project_name": project.name,
                "project_created": project_created,
                "reporting_currency": reporting_currency,
                "seeded_documents": seed_info["seeded_documents"],
                "generated_at_utc": _utc_now().isoformat(),
            },
            ensure_ascii=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
