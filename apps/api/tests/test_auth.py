from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_auth_me_returns_default_development_user() -> None:
    response = client.get("/auth/me")
    assert response.status_code == 200
    assert response.json() == {
        "user_id": "dev-user",
        "role": "analyst",
        "tenant_id": "dev-tenant",
    }


def test_publish_authorization_allows_board_member() -> None:
    response = client.get(
        "/auth/authorizations/publish",
        headers={"x-user-role": "board_member"},
    )
    assert response.status_code == 200
    assert response.json()["allowed"] is True


def test_publish_authorization_denies_analyst() -> None:
    response = client.get(
        "/auth/authorizations/publish",
        headers={"x-user-role": "analyst"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient role permissions for this operation."


def test_invalid_role_returns_401() -> None:
    response = client.get(
        "/auth/me",
        headers={"x-user-role": "invalid_role"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or unsupported role."

