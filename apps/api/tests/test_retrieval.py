# Bu test dosyasi, retrieval davranisini dogrular.

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.core import Project, RetrievalRun, Tenant
from app.core.settings import settings


def _seed_tenants_projects(db: Session) -> dict[str, str]:
    tenant_a = Tenant(name="Tenant A", slug="tenant-a")
    tenant_b = Tenant(name="Tenant B", slug="tenant-b")
    db.add_all([tenant_a, tenant_b])
    db.flush()

    project_a1 = Project(tenant_id=tenant_a.id, name="Project A1", code="PRJ-A1", reporting_currency="TRY")
    project_a2 = Project(tenant_id=tenant_a.id, name="Project A2", code="PRJ-A2", reporting_currency="TRY")
    project_b1 = Project(tenant_id=tenant_b.id, name="Project B1", code="PRJ-B1", reporting_currency="TRY")
    db.add_all([project_a1, project_a2, project_b1])
    db.commit()

    return {
        "tenant_a": tenant_a.id,
        "tenant_b": tenant_b.id,
        "project_a1": project_a1.id,
        "project_a2": project_a2.id,
        "project_b1": project_b1.id,
    }


def _write_local_index(root: Path, index_name: str, rows: dict[str, dict[str, object]]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"{index_name}.json"
    target.write_text(json.dumps(rows, ensure_ascii=True, indent=2), encoding="utf-8")


def test_retrieval_query_filters_by_tenant_project_and_persists_run(tmp_path: Path) -> None:
    db_file = tmp_path / "test_retrieval.db"
    engine = create_engine(f"sqlite:///{db_file}")
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    local_index_root = tmp_path / "search-index"
    index_name = "test-esg-index"

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    original_use_local = settings.azure_ai_search_use_local
    original_root = settings.local_search_index_root
    original_index_name = settings.azure_ai_search_index_name
    settings.azure_ai_search_use_local = True
    settings.local_search_index_root = str(local_index_root)
    settings.azure_ai_search_index_name = index_name

    client = TestClient(app)

    try:
        with TestingSessionLocal() as session:
            ids = _seed_tenants_projects(session)

        _write_local_index(
            local_index_root,
            index_name,
            {
                "chk-1": {
                    "id": "chk-1",
                    "chunk_id": "chk-1",
                    "tenant_id": ids["tenant_a"],
                    "project_id": ids["project_a1"],
                    "source_document_id": "doc-1",
                    "chunk_index": 0,
                    "page": 1,
                    "section_label": "Scope 2",
                    "token_count": 6,
                    "content": "Scope 2 emissions decreased in 2025 due to renewable electricity usage.",
                },
                "chk-2": {
                    "id": "chk-2",
                    "chunk_id": "chk-2",
                    "tenant_id": ids["tenant_a"],
                    "project_id": ids["project_a1"],
                    "source_document_id": "doc-2",
                    "chunk_index": 1,
                    "page": 2,
                    "section_label": "Energy",
                    "token_count": 7,
                    "content": "Renewable electricity share increased and emissions intensity improved.",
                },
                "chk-3": {
                    "id": "chk-3",
                    "chunk_id": "chk-3",
                    "tenant_id": ids["tenant_a"],
                    "project_id": ids["project_a2"],
                    "source_document_id": "doc-3",
                    "chunk_index": 0,
                    "page": 3,
                    "section_label": "Other project",
                    "token_count": 5,
                    "content": "This chunk belongs to another project and must be filtered out.",
                },
                "chk-4": {
                    "id": "chk-4",
                    "chunk_id": "chk-4",
                    "tenant_id": ids["tenant_b"],
                    "project_id": ids["project_b1"],
                    "source_document_id": "doc-4",
                    "chunk_index": 0,
                    "page": 4,
                    "section_label": "Other tenant",
                    "token_count": 5,
                    "content": "This chunk belongs to another tenant and must be filtered out.",
                },
            },
        )

        response = client.post(
            "/retrieval/query",
            json={
                "tenant_id": ids["tenant_a"],
                "project_id": ids["project_a1"],
                "query_text": "scope 2 emissions renewable electricity",
                "top_k": 1,
                "retrieval_mode": "hybrid",
            },
            headers={"x-user-role": "analyst"},
        )
        assert response.status_code == 200
        body = response.json()

        assert len(body["evidence"]) == 1
        assert body["evidence"][0]["chunk_id"] in {"chk-1", "chk-2"}
        assert body["diagnostics"]["backend"] == "local_json"
        assert body["diagnostics"]["top_k"] == 1
        assert body["diagnostics"]["result_count"] == 1
        assert body["diagnostics"]["filter_hit_count"] == 2
        assert body["diagnostics"]["coverage"] > 0.0
        assert body["diagnostics"]["coverage"] <= 1.0
        assert body["diagnostics"]["best_score"] > 0.0
        assert body["diagnostics"]["quality_gate_passed"] is True
        assert body["diagnostics"]["index_name"] == index_name
        assert body["diagnostics"]["applied_filters"] == {
            "tenant_id": ids["tenant_a"],
            "project_id": ids["project_a1"],
        }

        with TestingSessionLocal() as session:
            run = session.get(RetrievalRun, body["retrieval_run_id"])
            assert run is not None
            assert run.tenant_id == ids["tenant_a"]
            assert run.project_id == ids["project_a1"]
            assert run.query_text == "scope 2 emissions renewable electricity"
            assert run.top_k == 1
            assert run.result_count == 1
            assert run.status == "completed"
    finally:
        settings.azure_ai_search_use_local = original_use_local
        settings.local_search_index_root = original_root
        settings.azure_ai_search_index_name = original_index_name
        app.dependency_overrides.clear()
        engine.dispose()


def test_retrieval_query_includes_latency_diagnostics(tmp_path: Path) -> None:
    db_file = tmp_path / "test_retrieval_latency.db"
    engine = create_engine(f"sqlite:///{db_file}")
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    local_index_root = tmp_path / "search-index"
    index_name = "test-esg-index-latency"

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    original_use_local = settings.azure_ai_search_use_local
    original_root = settings.local_search_index_root
    original_index_name = settings.azure_ai_search_index_name
    settings.azure_ai_search_use_local = True
    settings.local_search_index_root = str(local_index_root)
    settings.azure_ai_search_index_name = index_name

    client = TestClient(app)

    try:
        with TestingSessionLocal() as session:
            ids = _seed_tenants_projects(session)

        _write_local_index(
            local_index_root,
            index_name,
            {
                "chk-latency": {
                    "id": "chk-latency",
                    "chunk_id": "chk-latency",
                    "tenant_id": ids["tenant_a"],
                    "project_id": ids["project_a1"],
                    "source_document_id": "doc-latency",
                    "chunk_index": 0,
                    "page": 1,
                    "section_label": "KPI",
                    "token_count": 4,
                    "content": "Water withdrawal baseline KPI for 2025.",
                }
            },
        )

        response = client.post(
            "/retrieval/query",
            json={
                "tenant_id": ids["tenant_a"],
                "project_id": ids["project_a1"],
                "query_text": "water withdrawal kpi",
                "top_k": 5,
                "retrieval_mode": "sparse",
            },
            headers={"x-user-role": "analyst"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["diagnostics"]["backend"] == "local_json"
        assert body["diagnostics"]["retrieval_mode"] == "sparse"
        assert body["diagnostics"]["latency_ms"] >= 0
        assert body["diagnostics"]["result_count"] == len(body["evidence"])
        assert body["diagnostics"]["filter_hit_count"] == 1
        assert body["diagnostics"]["coverage"] > 0.0
        assert body["diagnostics"]["best_score"] > 0.0
        assert body["diagnostics"]["quality_gate_passed"] is True
    finally:
        settings.azure_ai_search_use_local = original_use_local
        settings.local_search_index_root = original_root
        settings.azure_ai_search_index_name = original_index_name
        app.dependency_overrides.clear()
        engine.dispose()


def test_retrieval_query_azure_path_uses_filter_and_returns_diagnostics(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_file = tmp_path / "test_retrieval_azure.db"
    engine = create_engine(f"sqlite:///{db_file}")
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    class _FakeSearchClient:
        def __init__(self) -> None:
            self.search_calls: list[dict[str, object]] = []

        def search(self, *, search_text: str, top: int, filter: str):  # noqa: A002
            self.search_calls.append(
                {
                    "search_text": search_text,
                    "top": top,
                    "filter": filter,
                }
            )
            return [
                {
                    "id": "chk-az-1",
                    "chunk_id": "chk-az-1",
                    "source_document_id": "doc-az-1",
                    "page": 6,
                    "content": "Climate risk and scope emissions mitigation controls.",
                    "@search.score": 2.1,
                    "section_label": "TSRS2 climate",
                    "chunk_index": 0,
                    "token_count": 8,
                }
            ]

    fake_client = _FakeSearchClient()
    monkeypatch.setattr(
        "app.services.retrieval._build_azure_search_client",
        lambda: fake_client,
    )

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    original_use_local = settings.azure_ai_search_use_local
    original_index_name = settings.azure_ai_search_index_name
    settings.azure_ai_search_use_local = False
    settings.azure_ai_search_index_name = "azure-esg-index"

    client = TestClient(app)

    try:
        with TestingSessionLocal() as session:
            ids = _seed_tenants_projects(session)

        response = client.post(
            "/retrieval/query",
            json={
                "tenant_id": ids["tenant_a"],
                "project_id": ids["project_a1"],
                "query_text": "scope emissions climate risk",
                "top_k": 3,
                "retrieval_mode": "hybrid",
            },
            headers={"x-user-role": "analyst"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["diagnostics"]["backend"] == "azure_ai_search"
        assert body["diagnostics"]["result_count"] == 1
        assert body["diagnostics"]["filter_hit_count"] == 1
        assert body["diagnostics"]["coverage"] > 0.0
        assert body["diagnostics"]["best_score"] > 0.0
        assert body["diagnostics"]["quality_gate_passed"] is True
        assert body["diagnostics"]["latency_ms"] >= 0

        assert len(fake_client.search_calls) == 1
        call = fake_client.search_calls[0]
        assert call["search_text"] == "scope emissions climate risk"
        assert call["top"] == 3
        assert call["filter"] == (
            f"tenant_id eq '{ids['tenant_a']}' and project_id eq '{ids['project_a1']}'"
        )
    finally:
        settings.azure_ai_search_use_local = original_use_local
        settings.azure_ai_search_index_name = original_index_name
        app.dependency_overrides.clear()
        engine.dispose()


def test_retrieval_query_returns_503_when_azure_endpoint_missing(tmp_path: Path) -> None:
    db_file = tmp_path / "test_retrieval_azure_error.db"
    engine = create_engine(f"sqlite:///{db_file}")
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    original_use_local = settings.azure_ai_search_use_local
    original_endpoint = settings.azure_ai_search_endpoint
    original_api_key = settings.azure_ai_search_api_key
    settings.azure_ai_search_use_local = False
    settings.azure_ai_search_endpoint = None
    settings.azure_ai_search_api_key = None

    client = TestClient(app)

    try:
        with TestingSessionLocal() as session:
            ids = _seed_tenants_projects(session)

        response = client.post(
            "/retrieval/query",
            json={
                "tenant_id": ids["tenant_a"],
                "project_id": ids["project_a1"],
                "query_text": "scope emissions climate risk",
                "top_k": 5,
                "retrieval_mode": "hybrid",
            },
            headers={"x-user-role": "analyst"},
        )
        assert response.status_code == 503
        assert "AZURE_AI_SEARCH_ENDPOINT must be set" in response.json()["detail"]
    finally:
        settings.azure_ai_search_use_local = original_use_local
        settings.azure_ai_search_endpoint = original_endpoint
        settings.azure_ai_search_api_key = original_api_key
        app.dependency_overrides.clear()
        engine.dispose()


def test_retrieval_query_small_to_big_expands_adjacent_context(tmp_path: Path) -> None:
    db_file = tmp_path / "test_retrieval_small_to_big.db"
    engine = create_engine(f"sqlite:///{db_file}")
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    local_index_root = tmp_path / "search-index"
    index_name = "test-esg-index-small-to-big"

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    original_use_local = settings.azure_ai_search_use_local
    original_root = settings.local_search_index_root
    original_index_name = settings.azure_ai_search_index_name
    settings.azure_ai_search_use_local = True
    settings.local_search_index_root = str(local_index_root)
    settings.azure_ai_search_index_name = index_name

    client = TestClient(app)

    try:
        with TestingSessionLocal() as session:
            ids = _seed_tenants_projects(session)

        _write_local_index(
            local_index_root,
            index_name,
            {
                "chk-s2b-0": {
                    "id": "chk-s2b-0",
                    "chunk_id": "chk-s2b-0",
                    "tenant_id": ids["tenant_a"],
                    "project_id": ids["project_a1"],
                    "source_document_id": "doc-s2b-1",
                    "chunk_index": 0,
                    "page": 10,
                    "section_label": "Scope 2",
                    "token_count": 10,
                    "content": "Scope 2 emissions dropped by renewable sourcing in 2025.",
                },
                "chk-s2b-1": {
                    "id": "chk-s2b-1",
                    "chunk_id": "chk-s2b-1",
                    "tenant_id": ids["tenant_a"],
                    "project_id": ids["project_a1"],
                    "source_document_id": "doc-s2b-1",
                    "chunk_index": 1,
                    "page": 10,
                    "section_label": "Scope 2",
                    "token_count": 9,
                    "content": "Adjacent paragraph details procurement contracts and certificate notes.",
                },
            },
        )

        response = client.post(
            "/retrieval/query",
            json={
                "tenant_id": ids["tenant_a"],
                "project_id": ids["project_a1"],
                "query_text": "scope 2 emissions 2025",
                "top_k": 1,
                "retrieval_mode": "hybrid",
                "retrieval_hints": {
                    "section_tags": ["Scope 2"],
                    "small_to_big": True,
                    "context_window": 1,
                },
            },
            headers={"x-user-role": "analyst"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["diagnostics"]["quality_gate_passed"] is True
        assert len(body["evidence"]) == 2
        chunk_ids = {row["chunk_id"] for row in body["evidence"]}
        assert chunk_ids == {"chk-s2b-0", "chk-s2b-1"}
    finally:
        settings.azure_ai_search_use_local = original_use_local
        settings.local_search_index_root = original_root
        settings.azure_ai_search_index_name = original_index_name
        app.dependency_overrides.clear()
        engine.dispose()


def test_retrieval_query_quality_gate_failure_returns_422_and_persists_run(
    tmp_path: Path,
) -> None:
    db_file = tmp_path / "test_retrieval_quality_gate.db"
    engine = create_engine(f"sqlite:///{db_file}")
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    local_index_root = tmp_path / "search-index"
    index_name = "test-esg-index-quality-gate"

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    original_use_local = settings.azure_ai_search_use_local
    original_root = settings.local_search_index_root
    original_index_name = settings.azure_ai_search_index_name
    settings.azure_ai_search_use_local = True
    settings.local_search_index_root = str(local_index_root)
    settings.azure_ai_search_index_name = index_name

    client = TestClient(app)

    try:
        with TestingSessionLocal() as session:
            ids = _seed_tenants_projects(session)

        _write_local_index(
            local_index_root,
            index_name,
            {
                "chk-qg-0": {
                    "id": "chk-qg-0",
                    "chunk_id": "chk-qg-0",
                    "tenant_id": ids["tenant_a"],
                    "project_id": ids["project_a1"],
                    "source_document_id": "doc-qg-1",
                    "chunk_index": 0,
                    "page": 4,
                    "section_label": "Energy",
                    "token_count": 6,
                    "content": "Low match content for unrelated query terms.",
                }
            },
        )

        response = client.post(
            "/retrieval/query",
            json={
                "tenant_id": ids["tenant_a"],
                "project_id": ids["project_a1"],
                "query_text": "scope 3 logistics emissions",
                "top_k": 3,
                "retrieval_mode": "hybrid",
                "min_coverage": 0.95,
            },
            headers={"x-user-role": "analyst"},
        )
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert "Retrieval quality gate failed" in detail["message"]
        assert detail["diagnostics"]["quality_gate_passed"] is False
        assert detail["diagnostics"]["coverage"] < 0.95

        with TestingSessionLocal() as session:
            rows = session.query(RetrievalRun).all()
            assert len(rows) == 1
            assert rows[0].status == "failed_quality_gate"
            assert rows[0].tenant_id == ids["tenant_a"]
            assert rows[0].project_id == ids["project_a1"]
    finally:
        settings.azure_ai_search_use_local = original_use_local
        settings.local_search_index_root = original_root
        settings.azure_ai_search_index_name = original_index_name
        app.dependency_overrides.clear()
        engine.dispose()


def test_retrieval_query_empty_result_fails_quality_gate_by_default(tmp_path: Path) -> None:
    db_file = tmp_path / "test_retrieval_empty_quality_gate.db"
    engine = create_engine(f"sqlite:///{db_file}")
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    local_index_root = tmp_path / "search-index"
    index_name = "test-esg-index-empty-quality-gate"

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    original_use_local = settings.azure_ai_search_use_local
    original_root = settings.local_search_index_root
    original_index_name = settings.azure_ai_search_index_name
    settings.azure_ai_search_use_local = True
    settings.local_search_index_root = str(local_index_root)
    settings.azure_ai_search_index_name = index_name

    client = TestClient(app)

    try:
        with TestingSessionLocal() as session:
            ids = _seed_tenants_projects(session)

        _write_local_index(
            local_index_root,
            index_name,
            {
                "chk-empty-0": {
                    "id": "chk-empty-0",
                    "chunk_id": "chk-empty-0",
                    "tenant_id": ids["tenant_a"],
                    "project_id": ids["project_a1"],
                    "source_document_id": "doc-empty-1",
                    "chunk_index": 0,
                    "page": 2,
                    "section_label": "Water",
                    "token_count": 5,
                    "content": "water usage baseline",
                }
            },
        )

        response = client.post(
            "/retrieval/query",
            json={
                "tenant_id": ids["tenant_a"],
                "project_id": ids["project_a1"],
                "query_text": "unmatched random tokens",
                "top_k": 3,
                "retrieval_mode": "sparse",
            },
            headers={"x-user-role": "analyst"},
        )
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert "result_count=0" in detail["message"]
        assert detail["diagnostics"]["result_count"] == 0
        assert detail["diagnostics"]["quality_gate_passed"] is False
    finally:
        settings.azure_ai_search_use_local = original_use_local
        settings.local_search_index_root = original_root
        settings.azure_ai_search_index_name = original_index_name
        app.dependency_overrides.clear()
        engine.dispose()
