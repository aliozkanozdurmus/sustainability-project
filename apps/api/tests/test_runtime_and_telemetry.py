# Bu test dosyasi, uygulama lifespan ve telemetry bootstrap davranisini dogrular.

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import create_app
from app.telemetry import setup_telemetry


def test_app_lifespan_binds_runtime_services_and_shuts_them_down(monkeypatch) -> None:
    events: list[tuple[str, object | None]] = []
    runtime_services = object()
    telemetry_runtime = object()

    def fake_build_runtime_services():
        events.append(("runtime_build", None))
        return runtime_services

    async def fake_shutdown_runtime_services(runtime):
        events.append(("runtime_shutdown", runtime))

    def fake_setup_telemetry(_app):
        events.append(("telemetry_setup", None))
        return telemetry_runtime

    def fake_shutdown_telemetry(runtime):
        events.append(("telemetry_shutdown", runtime))

    monkeypatch.setattr("app.main.build_app_runtime_services", fake_build_runtime_services)
    monkeypatch.setattr("app.main.shutdown_app_runtime_services", fake_shutdown_runtime_services)
    monkeypatch.setattr("app.main.setup_telemetry", fake_setup_telemetry)
    monkeypatch.setattr("app.main.shutdown_telemetry", fake_shutdown_telemetry)

    app = create_app()

    with TestClient(app) as client:
        response = client.get("/health/live")
        assert response.status_code == 200
        assert app.state.runtime_services is runtime_services
        assert app.state.telemetry is telemetry_runtime

    assert ("runtime_build", None) in events
    assert ("telemetry_setup", None) in events
    assert ("telemetry_shutdown", telemetry_runtime) in events
    assert ("runtime_shutdown", runtime_services) in events


def test_setup_telemetry_returns_disabled_runtime_when_packages_missing(monkeypatch) -> None:
    monkeypatch.setattr("app.telemetry.settings.otel_enabled", True)
    monkeypatch.setattr("app.telemetry._import_opentelemetry", lambda: None)

    app = FastAPI()
    runtime = setup_telemetry(app)

    assert runtime.enabled is False
