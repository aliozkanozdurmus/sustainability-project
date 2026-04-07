# Bu test dosyasi, health davranisini dogrular.

from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import app


client = TestClient(app)


class _HealthyDb:
    def execute(self, _statement) -> None:
        return None


class _FailingDb:
    def execute(self, _statement) -> None:
        raise RuntimeError("db down")


def test_liveness_returns_200() -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive", "service": "api"}


def test_readiness_returns_200() -> None:
    app.dependency_overrides[get_db] = lambda: _HealthyDb()
    response = client.get("/health/ready")
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"app": "ok", "database": "ok"}}


def test_readiness_returns_503_when_database_check_fails() -> None:
    app.dependency_overrides[get_db] = lambda: _FailingDb()
    response = client.get("/health/ready")
    app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["detail"]["status"] == "not_ready"
    assert response.json()["detail"]["checks"] == {"app": "ok", "database": "error"}
