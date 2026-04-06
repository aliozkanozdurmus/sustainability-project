from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import require_roles
from app.db.session import get_db
from app.models.core import CanonicalFact, ConnectorSyncJob, IntegrationConfig, Project
from app.schemas.auth import CurrentUser
from app.schemas.integrations import (
    ConnectorSyncJobResponse,
    IntegrationConfigCreateRequest,
    IntegrationConfigResponse,
    IntegrationSyncRequest,
    IntegrationSyncResponse,
    ProjectFactResponse,
    ProjectFactsResponse,
)
from app.services.integrations import normalize_connector_type, run_connector_sync, upsert_integration_config

router = APIRouter(tags=["integrations"])
INTEGRATION_MUTATION_ROLES = ("admin", "compliance_manager", "analyst")
INTEGRATION_READ_ROLES = (*INTEGRATION_MUTATION_ROLES, "auditor_readonly")


def _to_integration_response(integration: IntegrationConfig) -> IntegrationConfigResponse:
    return IntegrationConfigResponse(
        id=integration.id,
        tenant_id=integration.tenant_id,
        project_id=integration.project_id,
        connector_type=integration.connector_type,
        display_name=integration.display_name,
        auth_mode=integration.auth_mode,
        base_url=integration.base_url,
        resource_path=integration.resource_path,
        status=integration.status,
        mapping_version=integration.mapping_version,
        last_cursor=integration.last_cursor,
        last_synced_at_utc=integration.last_synced_at.isoformat() if integration.last_synced_at else None,
    )


def _to_sync_job_response(job: ConnectorSyncJob, integration: IntegrationConfig) -> ConnectorSyncJobResponse:
    return ConnectorSyncJobResponse(
        job_id=job.id,
        integration_config_id=job.integration_config_id,
        tenant_id=job.tenant_id,
        project_id=job.project_id,
        connector_type=integration.connector_type,
        status=job.status,
        current_stage=job.current_stage,
        record_count=job.record_count,
        inserted_count=job.inserted_count,
        updated_count=job.updated_count,
        cursor_before=job.cursor_before,
        cursor_after=job.cursor_after,
        error_message=job.error_message,
        started_at_utc=job.started_at.isoformat() if job.started_at else None,
        completed_at_utc=job.completed_at.isoformat() if job.completed_at else None,
        diagnostics=job.diagnostics_json or {},
    )


@router.post(
    "/integrations/connectors",
    response_model=IntegrationConfigResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_or_update_integration_connector(
    payload: IntegrationConfigCreateRequest,
    user: CurrentUser = Depends(require_roles(*INTEGRATION_MUTATION_ROLES)),
    db: Session = Depends(get_db),
) -> IntegrationConfigResponse:
    _ = user
    project = db.scalar(
        select(Project).where(
            Project.id == payload.project_id,
            Project.tenant_id == payload.tenant_id,
        )
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found for tenant.")

    integration = upsert_integration_config(
        db=db,
        tenant_id=payload.tenant_id,
        project_id=payload.project_id,
        connector_type=normalize_connector_type(payload.connector_type),
        display_name=payload.display_name.strip(),
        auth_mode=payload.auth_mode.strip(),
        base_url=payload.base_url.strip() if payload.base_url else None,
        resource_path=payload.resource_path.strip() if payload.resource_path else None,
        mapping_version=payload.mapping_version.strip(),
        connection_payload=payload.connection_payload,
        sample_payload=payload.sample_payload,
    )
    db.commit()
    db.refresh(integration)
    return _to_integration_response(integration)


@router.post(
    "/integrations/sync",
    response_model=IntegrationSyncResponse,
    status_code=status.HTTP_200_OK,
)
async def sync_integrations(
    payload: IntegrationSyncRequest,
    user: CurrentUser = Depends(require_roles(*INTEGRATION_MUTATION_ROLES)),
    db: Session = Depends(get_db),
) -> IntegrationSyncResponse:
    _ = user
    project = db.scalar(
        select(Project).where(
            Project.id == payload.project_id,
            Project.tenant_id == payload.tenant_id,
        )
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found for tenant.")

    query = select(IntegrationConfig).where(
        IntegrationConfig.project_id == payload.project_id,
        IntegrationConfig.tenant_id == payload.tenant_id,
        IntegrationConfig.status == "active",
    )
    if payload.connector_ids:
        query = query.where(IntegrationConfig.id.in_(payload.connector_ids))
    integrations = db.scalars(query.order_by(IntegrationConfig.connector_type.asc())).all()
    if not integrations:
        raise HTTPException(status_code=404, detail="No active integrations found for project.")

    jobs: list[ConnectorSyncJobResponse] = []
    for integration in integrations:
        job = run_connector_sync(db=db, integration=integration)
        jobs.append(_to_sync_job_response(job, integration))
    db.commit()
    return IntegrationSyncResponse(jobs=jobs, synced_connector_count=len(jobs))


@router.get(
    "/integrations/sync-jobs/{job_id}",
    response_model=ConnectorSyncJobResponse,
    status_code=status.HTTP_200_OK,
)
async def get_sync_job(
    job_id: str,
    tenant_id: str = Query(min_length=1),
    project_id: str = Query(min_length=1),
    user: CurrentUser = Depends(require_roles(*INTEGRATION_READ_ROLES)),
    db: Session = Depends(get_db),
) -> ConnectorSyncJobResponse:
    _ = user
    job = db.scalar(
        select(ConnectorSyncJob).where(
            ConnectorSyncJob.id == job_id,
            ConnectorSyncJob.tenant_id == tenant_id,
            ConnectorSyncJob.project_id == project_id,
        )
    )
    if job is None:
        raise HTTPException(status_code=404, detail="Sync job not found.")
    integration = db.get(IntegrationConfig, job.integration_config_id)
    if integration is None:
        raise HTTPException(status_code=404, detail="Integration not found for sync job.")
    return _to_sync_job_response(job, integration)


@router.get(
    "/projects/{project_id}/facts",
    response_model=ProjectFactsResponse,
    status_code=status.HTTP_200_OK,
)
async def list_project_facts(
    project_id: str,
    tenant_id: str = Query(min_length=1),
    metric_code: str | None = Query(default=None),
    user: CurrentUser = Depends(require_roles(*INTEGRATION_READ_ROLES)),
    db: Session = Depends(get_db),
) -> ProjectFactsResponse:
    _ = user
    project = db.scalar(
        select(Project).where(
            Project.id == project_id,
            Project.tenant_id == tenant_id,
        )
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found for tenant.")

    query = select(CanonicalFact).where(
        CanonicalFact.project_id == project_id,
        CanonicalFact.tenant_id == tenant_id,
    )
    if metric_code and metric_code.strip():
        query = query.where(CanonicalFact.metric_code == metric_code.strip().upper())

    rows = db.scalars(query.order_by(CanonicalFact.metric_code.asc(), CanonicalFact.period_key.desc())).all()
    items = [
        ProjectFactResponse(
            fact_id=row.id,
            metric_code=row.metric_code,
            metric_name=row.metric_name,
            period_key=row.period_key,
            unit=row.unit,
            value_numeric=row.value_numeric,
            value_text=row.value_text,
            source_system=row.source_system,
            source_record_id=row.source_record_id,
            owner=row.owner,
            freshness_at_utc=row.freshness_at.isoformat() if row.freshness_at else None,
            confidence_score=row.confidence_score,
            trace_ref=row.trace_ref,
            metadata=row.metadata_json or {},
        )
        for row in rows
    ]
    return ProjectFactsResponse(items=items, total=len(items))
