from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AuditLog
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


def test_login_is_blocked_after_repeated_failures(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch, db: Session
) -> None:
    monkeypatch.setattr(get_settings(), "login_max_failures_per_user", 3)
    for _ in range(3):
        response = client.post("/api/v1/auth/login", json={"username": "t_admin", "password": "wrong"})
        assert response.status_code == 401
    # The correct password is not even checked while the account is blocked.
    blocked = client.post("/api/v1/auth/login", json={"username": "t_admin", "password": PASSWORD})
    assert blocked.status_code == 429
    assert blocked.json()["detail"]["code"] == "too_many_attempts"
    assert 0 < int(blocked.headers["Retry-After"]) <= get_settings().login_lockout_minutes * 60
    # Other accounts are not affected (the per-address limit is far higher).
    other = client.post("/api/v1/auth/login", json={"username": "t_gask", "password": PASSWORD})
    assert other.status_code == 200

    failures = db.scalars(select(AuditLog).where(AuditLog.action == "auth.login_failed")).all()
    assert len(failures) == 3
    assert {entry.entity_id for entry in failures} == {world.users["admin"].id}
    assert failures[0].after == {"username": "t_admin"}


def test_login_is_blocked_per_address_across_usernames(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "login_max_failures_per_ip", 2)
    for username in ("guess1", "guess2"):
        assert client.post("/api/v1/auth/login", json={"username": username, "password": "x"}).status_code == 401
    response = client.post("/api/v1/auth/login", json={"username": "t_gask", "password": PASSWORD})
    assert response.status_code == 429


def test_successful_login_clears_account_failures(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "login_max_failures_per_user", 2)
    assert client.post("/api/v1/auth/login", json={"username": "t_admin", "password": "wrong"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"username": "t_admin", "password": PASSWORD}).status_code == 200
    assert client.post("/api/v1/auth/login", json={"username": "t_admin", "password": "wrong"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"username": "t_admin", "password": PASSWORD}).status_code == 200
