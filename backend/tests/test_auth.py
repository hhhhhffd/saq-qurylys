from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.security import create_access_token
from tests.conftest import PASSWORD, World, auth


def test_login_returns_token_and_user(client: TestClient, world: World) -> None:
    response = client.post("/api/v1/auth/login", json={"username": "T_MIO_UST", "password": PASSWORD})
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["username"] == "t_mio_ust"
    assert body["user"]["role"] == "mio_officer"
    assert "password_hash" not in body["user"]

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["id"] == world.users["mio_ust"].id


def test_login_rejects_wrong_password_and_unknown_user(client: TestClient, world: World) -> None:
    for payload in (
        {"username": "t_admin", "password": "wrong"},
        {"username": "nobody", "password": PASSWORD},
    ):
        response = client.post("/api/v1/auth/login", json=payload)
        assert response.status_code == 401
        assert response.json()["detail"]["code"] == "invalid_credentials"


def test_inactive_user_cannot_login_or_use_token(client: TestClient, world: World) -> None:
    user = world.users["admin"]
    headers = auth(user)
    user.is_active = False
    assert client.post("/api/v1/auth/login", json={"username": "t_admin", "password": PASSWORD}).status_code == 401
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_missing_malformed_and_expired_tokens(client: TestClient, world: World) -> None:
    assert client.get("/api/v1/auth/me").json()["detail"]["code"] == "not_authenticated"
    assert client.get("/api/v1/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401
    expired = create_access_token(world.users["admin"].id, now=datetime.now(UTC) - timedelta(days=2))
    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "invalid_token"


def test_validation_errors_use_contract_format(client: TestClient) -> None:
    response = client.post("/api/v1/auth/login", json={"username": "x"})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "validation_error"
