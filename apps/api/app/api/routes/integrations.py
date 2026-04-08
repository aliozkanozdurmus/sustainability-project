# Bu route, integrations uc noktasinin HTTP giris katmanini tanimlar.

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import require_roles
from app.db.session import get_db
from app.models.core import (
    CanonicalFact,
    ConnectorAgent,
    ConnectorArtifact,
    ConnectorOperationRun,
    ConnectorSyncJob,
    IntegrationConfig,
    Project,
)
from app.schemas.auth import CurrentUser
from app.schemas.integrations import (
    ConnectorAgentHeartbeatRequest,
    ConnectorAgentRegisterRequest,
    ConnectorAgentResponse,
    ConnectorArtifactResponse,
    ConnectorClaimNextOperationResponse,
    ConnectorOperationRequest,
    ConnectorOperationResponse,
    ConnectorPreviewSyncRequest,
    ConnectorReplayRequest,
    ConnectorSyncJobResponse,
    IntegrationConfigCreateRequest,
    IntegrationConfigResponse,
    IntegrationSyncRequest,
    IntegrationSyncResponse,
    ProjectFactResponse,
    ProjectFactsResponse,
)
from app.services.blob_storage import get_blob_storage_service
from app.services.integrations import (
    claim_next_connector_operation,
    execute_connector_operation,
    get_assigned_agent_status,
    heartbeat_connector_agent,
    normalize_connector_type,
    redact_connection_profile,
    register_connector_agent,
    run_connector_operation,
    run_connector_sync,
    upsert_integration_config,
)

router = APIRouter(tags=["integrations"])
INTEGRATION_MUTATION_ROLES = ("admin", "compliance_manager", "analyst")
INTEGRATION_READ_ROLES = (*INTEGRATION_MUTATION_ROLES, "auditor_readonly")


def _as_iso(value) -> str | None:
    return value.isoformat() if value else None


def _to_integration_response(db: Session, integration: IntegrationConfig) -> IntegrationConfigResponse:
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
        certified_variant=integration.certified_variant,
        product_version=integration.product_version,
        support_tier=integration.support_tier,  # type: ignore[arg-type]
        connectivity_mode=integration.connectivity_mode,
        credential_ref=integration.credential_ref,
        health_band=integration.health_band,  # type: ignore[arg-type]
        health_status=integration.health_status_json or None,
        assigned_agent_id=integration.assigned_agent_id,
        normalization_policy=integration.normalization_policy_json or {},
        connection_profile=redact_connection_profile(integration.connection_payload or {}),
        last_cursor=integration.last_cursor,
        last_discovered_at_utc=_as_iso(integration.last_discovered_at),
        last_preflight_at_utc=_as_iso(integration.last_preflight_at),
        last_preview_sync_at_utc=_as_iso(integration.last_preview_sync_at),
        last_synced_at_utc=_as_iso(integration.last_synced_at),
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
        started_at_utc=_as_iso(job.started_at),
        completed_at_utc=_as_iso(job.completed_at),
        diagnostics=job.diagnostics_json or {},
    )


def _to_agent_response(agent: ConnectorAgent) -> ConnectorAgentResponse:
    return ConnectorAgentResponse(
        agent_id=agent.id,
        tenant_id=agent.tenant_id,
        project_id=agent.project_id,
        agent_key=agent.agent_key,
        display_name=agent.display_name,
        agent_kind=agent.agent_kind,  # type: ignore[arg-type]
        status=agent.status,
        version=agent.version,
        hostname=agent.hostname,
        supported_connectors=agent.supported_connectors_json or [],
        capabilities=agent.capabilities_json or [],
        metadata=agent.metadata_json or {},
        last_heartbeat_at_utc=_as_iso(agent.last_heartbeat_at),
    )


def _to_artifact_response(artifact: ConnectorArtifact) -> ConnectorArtifactResponse:
    return ConnectorArtifactResponse(
        artifact_id=artifact.id,
        integration_config_id=artifact.integration_config_id,
        connector_operation_run_id=artifact.connector_operation_run_id,
        artifact_type=artifact.artifact_type,
        filename=artifact.filename,
        content_type=artifact.content_type,
        size_bytes=artifact.size_bytes,
        checksum=artifact.checksum,
        created_at_utc=artifact.created_at.isoformat(),
        download_path=(
            f"/integrations/connectors/{artifact.integration_config_id}/artifacts/{artifact.id}"
            f"?tenant_id={artifact.tenant_id}&project_id={artifact.project_id}"
        ),
        metadata=artifact.artifact_metadata_json or {},
    )


def _to_operation_response(
    db: Session,
    operation: ConnectorOperationRun,
    integration: IntegrationConfig,
) -> ConnectorOperationResponse:
    artifact = db.scalar(
        select(ConnectorArtifact)
        .where(ConnectorArtifact.connector_operation_run_id == operation.id)
        .order_by(ConnectorArtifact.created_at.desc())
    )
    return ConnectorOperationResponse(
        operation_id=operation.id,
        integration_config_id=operation.integration_config_id,
        tenant_id=operation.tenant_id,
        project_id=operation.project_id,
        connector_type=operation.connector_type,
        operation_type=operation.operation_type,  # type: ignore[arg-type]
        status=operation.status,
        current_stage=operation.current_stage,
        replay_mode=operation.replay_mode,  # type: ignore[arg-type]
        assigned_agent_id=operation.assigned_agent_id,
        support_tier=integration.support_tier,  # type: ignore[arg-type]
        health_band=integration.health_band,  # type: ignore[arg-type]
        operator_message=operation.operator_message,
        support_hint=operation.support_hint,
        recommended_action=operation.recommended_action,
        retryable=operation.retryable,
        error_code=operation.error_code,
        error_message=operation.error_message,
        result=operation.result_payload_json or {},
        diagnostics=operation.diagnostics_json or {},
        started_at_utc=_as_iso(operation.started_at),
        completed_at_utc=_as_iso(operation.completed_at),
        artifact=_to_artifact_response(artifact) if artifact else None,
    )


def _require_project(db: Session, tenant_id: str, project_id: str) -> Project:
    project = db.scalar(
        select(Project).where(
            Project.id == project_id,
            Project.tenant_id == tenant_id,
        )
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found for tenant.")
    return project


def _require_integration(db: Session, integration_id: str, tenant_id: str, project_id: str) -> IntegrationConfig:
    integration = db.scalar(
        select(IntegrationConfig).where(
            IntegrationConfig.id == integration_id,
            IntegrationConfig.tenant_id == tenant_id,
            IntegrationConfig.project_id == project_id,
        )
    )
    if integration is None:
        raise HTTPException(status_code=404, detail="Integration not found for tenant/project.")
    return integration


def _run_operation(
    *,
    db: Session,
    integration: IntegrationConfig,
    operation_type: str,
    requested_by_user_id: str,
    replay_mode: str | None = None,
    preview_limit: int = 20,
    backfill_window_days: int | None = None,
) -> ConnectorOperationResponse:
    operation = run_connector_operation(
        db=db,
        integration=integration,
        operation_type=operation_type,
        requested_by_user_id=requested_by_user_id,
        replay_mode=replay_mode,
        preview_limit=preview_limit,
        backfill_window_days=backfill_window_days,
    )
    db.commit()
    db.refresh(integration)
    db.refresh(operation)
    return _to_operation_response(db, operation, integration)


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
    project = _require_project(db, payload.tenant_id, payload.project_id)
    try:
        integration = upsert_integration_config(
            db=db,
            tenant_id=payload.tenant_id,
            project_id=payload.project_id,
            connector_type=normalize_connector_type(payload.connector_type),
            display_name=payload.display_name,
            auth_mode=payload.auth_mode,
            base_url=payload.base_url.strip() if payload.base_url else None,
            resource_path=payload.resource_path.strip() if payload.resource_path else None,
            mapping_version=payload.mapping_version.strip(),
            certified_variant=payload.certified_variant,
            product_version=payload.product_version,
            connectivity_mode=payload.connectivity_mode,
            credential_ref=payload.credential_ref,
            assigned_agent_id=payload.assigned_agent_id,
            connection_profile=payload.connection_profile.model_dump(exclude_none=True),
            normalization_policy=payload.normalization_policy,
            sample_payload=payload.sample_payload,
            connection_payload=payload.connection_payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(project)
    db.refresh(integration)
    return _to_integration_response(db, integration)


@router.get("/integrations/connectors/{integration_id}", response_model=IntegrationConfigResponse, status_code=status.HTTP_200_OK)
async def get_integration_connector(
    integration_id: str,
    tenant_id: str = Query(min_length=1),
    project_id: str = Query(min_length=1),
    user: CurrentUser = Depends(require_roles(*INTEGRATION_READ_ROLES)),
    db: Session = Depends(get_db),
) -> IntegrationConfigResponse:
    _ = user
    integration = _require_integration(db, integration_id, tenant_id, project_id)
    return _to_integration_response(db, integration)


@router.post("/integrations/agents/register", response_model=ConnectorAgentResponse, status_code=status.HTTP_200_OK)
async def register_agent(
    payload: ConnectorAgentRegisterRequest,
    user: CurrentUser = Depends(require_roles(*INTEGRATION_MUTATION_ROLES)),
    db: Session = Depends(get_db),
) -> ConnectorAgentResponse:
    _ = user
    agent = register_connector_agent(
        db=db,
        tenant_id=payload.tenant_id,
        project_id=payload.project_id,
        agent_key=payload.agent_key.strip(),
        display_name=payload.display_name.strip(),
        agent_kind=payload.agent_kind,
        version=payload.version,
        hostname=payload.hostname,
        supported_connectors=payload.supported_connectors,
        capabilities=payload.capabilities,
        metadata=payload.metadata,
    )
    db.commit()
    db.refresh(agent)
    return _to_agent_response(agent)


@router.post("/integrations/agents/{agent_id}/heartbeat", response_model=ConnectorAgentResponse, status_code=status.HTTP_200_OK)
async def heartbeat_agent(
    agent_id: str,
    payload: ConnectorAgentHeartbeatRequest,
    user: CurrentUser = Depends(require_roles(*INTEGRATION_MUTATION_ROLES)),
    db: Session = Depends(get_db),
) -> ConnectorAgentResponse:
    _ = user
    agent = db.get(ConnectorAgent, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Connector agent not found.")
    agent = heartbeat_connector_agent(
        db=db,
        agent=agent,
        status=payload.status,
        version=payload.version,
        hostname=payload.hostname,
        active_operation_id=payload.active_operation_id,
        metrics=payload.metrics,
    )
    db.commit()
    db.refresh(agent)
    return _to_agent_response(agent)


@router.post("/integrations/agents/{agent_id}/claim-next", response_model=ConnectorClaimNextOperationResponse, status_code=status.HTTP_200_OK)
async def claim_next_operation(
    agent_id: str,
    user: CurrentUser = Depends(require_roles(*INTEGRATION_MUTATION_ROLES)),
    db: Session = Depends(get_db),
) -> ConnectorClaimNextOperationResponse:
    _ = user
    agent = db.get(ConnectorAgent, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Connector agent not found.")
    operation = claim_next_connector_operation(db=db, agent=agent)
    if operation is None:
        db.commit()
        return ConnectorClaimNextOperationResponse(operation=None)
    integration = db.get(IntegrationConfig, operation.integration_config_id)
    if integration is None:
        raise HTTPException(status_code=404, detail="Integration not found for queued operation.")
    db.commit()
    db.refresh(operation)
    return ConnectorClaimNextOperationResponse(operation=_to_operation_response(db, operation, integration))


@router.post("/integrations/connectors/{integration_id}/operations/{operation_id}/execute", response_model=ConnectorOperationResponse, status_code=status.HTTP_200_OK)
async def execute_claimed_operation(
    integration_id: str,
    operation_id: str,
    preview_limit: int = Query(default=20, ge=1, le=20),
    backfill_window_days: int | None = Query(default=None, ge=1, le=90),
    user: CurrentUser = Depends(require_roles(*INTEGRATION_MUTATION_ROLES)),
    db: Session = Depends(get_db),
) -> ConnectorOperationResponse:
    _ = user
    operation = db.scalar(select(ConnectorOperationRun).where(ConnectorOperationRun.id == operation_id))
    if operation is None:
        raise HTTPException(status_code=404, detail="Connector operation not found.")
    integration = _require_integration(db, integration_id, operation.tenant_id, operation.project_id)
    if operation.status == "completed" or operation.status == "failed":
        return _to_operation_response(db, operation, integration)
    operation = execute_connector_operation(
        db=db,
        integration=integration,
        operation=operation,
        preview_limit=preview_limit,
        backfill_window_days=backfill_window_days,
    )
    db.commit()
    db.refresh(integration)
    db.refresh(operation)
    return _to_operation_response(db, operation, integration)


@router.post("/integrations/connectors/{integration_id}/discover", response_model=ConnectorOperationResponse, status_code=status.HTTP_200_OK)
async def discover_connector(
    integration_id: str,
    payload: ConnectorOperationRequest,
    user: CurrentUser = Depends(require_roles(*INTEGRATION_MUTATION_ROLES)),
    db: Session = Depends(get_db),
) -> ConnectorOperationResponse:
    integration = _require_integration(db, integration_id, payload.tenant_id, payload.project_id)
    return _run_operation(
        db=db,
        integration=integration,
        operation_type="discover",
        requested_by_user_id=user.user_id,
    )


@router.post("/integrations/connectors/{integration_id}/preflight", response_model=ConnectorOperationResponse, status_code=status.HTTP_200_OK)
async def preflight_connector(
    integration_id: str,
    payload: ConnectorOperationRequest,
    user: CurrentUser = Depends(require_roles(*INTEGRATION_MUTATION_ROLES)),
    db: Session = Depends(get_db),
) -> ConnectorOperationResponse:
    integration = _require_integration(db, integration_id, payload.tenant_id, payload.project_id)
    return _run_operation(
        db=db,
        integration=integration,
        operation_type="preflight",
        requested_by_user_id=user.user_id,
    )


@router.post("/integrations/connectors/{integration_id}/preview-sync", response_model=ConnectorOperationResponse, status_code=status.HTTP_200_OK)
async def preview_sync_connector(
    integration_id: str,
    payload: ConnectorPreviewSyncRequest,
    user: CurrentUser = Depends(require_roles(*INTEGRATION_MUTATION_ROLES)),
    db: Session = Depends(get_db),
) -> ConnectorOperationResponse:
    integration = _require_integration(db, integration_id, payload.tenant_id, payload.project_id)
    return _run_operation(
        db=db,
        integration=integration,
        operation_type="preview_sync",
        requested_by_user_id=user.user_id,
        preview_limit=payload.limit,
    )


@router.post("/integrations/connectors/{integration_id}/replay", response_model=ConnectorOperationResponse, status_code=status.HTTP_200_OK)
async def replay_connector(
    integration_id: str,
    payload: ConnectorReplayRequest,
    user: CurrentUser = Depends(require_roles(*INTEGRATION_MUTATION_ROLES)),
    db: Session = Depends(get_db),
) -> ConnectorOperationResponse:
    integration = _require_integration(db, integration_id, payload.tenant_id, payload.project_id)
    return _run_operation(
        db=db,
        integration=integration,
        operation_type="replay",
        requested_by_user_id=user.user_id,
        replay_mode=payload.mode,
        backfill_window_days=payload.backfill_window_days,
    )


@router.post("/integrations/connectors/{integration_id}/support-bundle", response_model=ConnectorOperationResponse, status_code=status.HTTP_200_OK)
async def export_support_bundle(
    integration_id: str,
    payload: ConnectorOperationRequest,
    user: CurrentUser = Depends(require_roles(*INTEGRATION_MUTATION_ROLES)),
    db: Session = Depends(get_db),
) -> ConnectorOperationResponse:
    integration = _require_integration(db, integration_id, payload.tenant_id, payload.project_id)
    return _run_operation(
        db=db,
        integration=integration,
        operation_type="support_bundle",
        requested_by_user_id=user.user_id,
    )


@router.get("/integrations/connectors/{integration_id}/operations/{operation_id}", response_model=ConnectorOperationResponse, status_code=status.HTTP_200_OK)
async def get_connector_operation(
    integration_id: str,
    operation_id: str,
    tenant_id: str = Query(min_length=1),
    project_id: str = Query(min_length=1),
    user: CurrentUser = Depends(require_roles(*INTEGRATION_READ_ROLES)),
    db: Session = Depends(get_db),
) -> ConnectorOperationResponse:
    _ = user
    integration = _require_integration(db, integration_id, tenant_id, project_id)
    operation = db.scalar(
        select(ConnectorOperationRun).where(
            ConnectorOperationRun.id == operation_id,
            ConnectorOperationRun.integration_config_id == integration.id,
            ConnectorOperationRun.tenant_id == tenant_id,
            ConnectorOperationRun.project_id == project_id,
        )
    )
    if operation is None:
        raise HTTPException(status_code=404, detail="Connector operation not found.")
    return _to_operation_response(db, operation, integration)


@router.get("/integrations/connectors/{integration_id}/artifacts/{artifact_id}", status_code=status.HTTP_200_OK)
async def download_connector_artifact(
    integration_id: str,
    artifact_id: str,
    tenant_id: str = Query(min_length=1),
    project_id: str = Query(min_length=1),
    user: CurrentUser = Depends(require_roles(*INTEGRATION_READ_ROLES)),
    db: Session = Depends(get_db),
) -> Response:
    _ = user
    _require_integration(db, integration_id, tenant_id, project_id)
    artifact = db.scalar(
        select(ConnectorArtifact).where(
            ConnectorArtifact.id == artifact_id,
            ConnectorArtifact.integration_config_id == integration_id,
            ConnectorArtifact.tenant_id == tenant_id,
            ConnectorArtifact.project_id == project_id,
        )
    )
    if artifact is None:
        raise HTTPException(status_code=404, detail="Connector artifact not found.")
    payload = get_blob_storage_service().download_bytes(artifact.storage_uri)
    return Response(
        content=payload,
        media_type=artifact.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{artifact.filename}"',
            "Content-Length": str(len(payload)),
        },
    )


@router.post("/integrations/sync", response_model=IntegrationSyncResponse, status_code=status.HTTP_200_OK)
async def sync_integrations(
    payload: IntegrationSyncRequest,
    user: CurrentUser = Depends(require_roles(*INTEGRATION_MUTATION_ROLES)),
    db: Session = Depends(get_db),
) -> IntegrationSyncResponse:
    _ = user
    _require_project(db, payload.tenant_id, payload.project_id)

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


@router.get("/integrations/sync-jobs/{job_id}", response_model=ConnectorSyncJobResponse, status_code=status.HTTP_200_OK)
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


@router.get("/projects/{project_id}/facts", response_model=ProjectFactsResponse, status_code=status.HTTP_200_OK)
async def list_project_facts(
    project_id: str,
    tenant_id: str = Query(min_length=1),
    metric_code: str | None = Query(default=None),
    user: CurrentUser = Depends(require_roles(*INTEGRATION_READ_ROLES)),
    db: Session = Depends(get_db),
) -> ProjectFactsResponse:
    _ = user
    _require_project(db, tenant_id, project_id)

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
            freshness_at_utc=_as_iso(row.freshness_at),
            confidence_score=row.confidence_score,
            trace_ref=row.trace_ref,
            metadata=row.metadata_json or {},
        )
        for row in rows
    ]
    return ProjectFactsResponse(items=items, total=len(items))
