import hashlib
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import storage
from app.config import get_settings
from app.models import AuditLog, Evidence
from app.models.enums import EvidenceKind
from tests.conftest import PDF_BYTES, PNG_BYTES, World, auth, make_object


def _post_document(client: TestClient, world: World, object_id: int, **fields: str) -> dict[str, Any]:
    data = {"doc_type": "dsu_permit", "number": "123-ДСУ", "issued_at": "2026-03-01", **fields}
    files = {"file": ("scan.png", PNG_BYTES, "image/png")}
    response = client.post(
        f"/api/v1/objects/{object_id}/documents", headers=auth(world.users["mio_ust"]), data=data, files=files
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def test_document_upload_creates_evidence_with_correct_sha256(
    client: TestClient, db: Session, world: World, bucket: str
) -> None:
    obj = make_object(db, world.ust)
    document = _post_document(client, world, obj.id, check_status="confirmed", check_source="housing_portal")

    assert document["check_status"] == "confirmed"
    assert document["checked_by"] == world.users["mio_ust"].id
    assert document["checked_at"] is not None
    [item] = document["evidence"]
    assert item["sha256"] == hashlib.sha256(PNG_BYTES).hexdigest()
    assert item["size_bytes"] == len(PNG_BYTES)
    assert item["kind"] == "document_scan"

    row = db.get(Evidence, item["id"])
    assert row is not None and row.document_id == document["id"] and row.kind is EvidenceKind.document_scan

    # The stored object matches, is locked, and the content endpoint streams it back unchanged.
    stored = storage.get_client().get_object(bucket, row.s3_key)
    try:
        assert hashlib.sha256(stored.read()).hexdigest() == row.sha256
    finally:
        stored.close()
        stored.release_conn()
    retention = storage.get_client().get_object_retention(bucket, row.s3_key)
    assert retention is not None and retention.mode == get_settings().evidence_lock_mode

    headers = auth(world.users["mio_ust"])
    meta = client.get(f"/api/v1/evidence/{row.id}", headers=headers).json()
    assert meta["sha256"] == row.sha256 and meta["lock_mode"] == "GOVERNANCE" and meta["has_tsa_token"] is False
    content = client.get(f"/api/v1/evidence/{row.id}/content", headers=headers)
    assert content.status_code == 200
    assert content.content == PNG_BYTES
    assert content.headers["content-type"] == "image/png"
    assert content.headers["x-content-type-options"] == "nosniff"

    audit = db.scalars(
        select(AuditLog).where(AuditLog.action == "document.create", AuditLog.entity_id == document["id"])
    ).one()
    assert audit.after["evidence_id"] == row.id


def test_document_without_file_and_with_blank_optional_fields(client: TestClient, db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    response = client.post(
        f"/api/v1/objects/{obj.id}/documents",
        headers=auth(world.users["mio_ust"]),
        data={"doc_type": "guarantee", "number": "", "issued_at": "", "check_source": ""},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["evidence"] == [] and body["issued_at"] is None and body["check_status"] == "checking"
    assert body["checked_by"] is None


def test_upload_validation(client: TestClient, db: Session, world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    obj = make_object(db, world.ust)
    headers = auth(world.users["mio_ust"])
    url = f"/api/v1/objects/{obj.id}/documents"

    spoofed = client.post(
        url, headers=headers, data={"doc_type": "psd"}, files={"file": ("x.png", b"<html><script>", "image/png")}
    )
    assert spoofed.status_code == 415
    assert spoofed.json()["detail"]["code"] == "unsupported_media_type"

    empty = client.post(
        url, headers=headers, data={"doc_type": "psd"}, files={"file": ("x.pdf", b"", "application/pdf")}
    )
    assert empty.status_code == 422

    monkeypatch.setattr(get_settings(), "max_upload_mb", 1)
    big = client.post(
        url,
        headers=headers,
        data={"doc_type": "psd"},
        files={"file": ("x.pdf", PDF_BYTES + b"0" * (1024 * 1024), "application/pdf")},
    )
    assert big.status_code == 413
    assert big.json()["detail"]["code"] == "file_too_large"


def test_patch_document_marks_checker(client: TestClient, db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    created = client.post(
        f"/api/v1/objects/{obj.id}/documents", headers=auth(world.users["mio_ust"]), data={"doc_type": "dsu_permit"}
    ).json()
    response = client.patch(
        f"/api/v1/documents/{created['id']}",
        headers=auth(world.users["mio_region"]),
        json={"check_status": "not_found", "check_source": "kazreestr", "note": "нет в реестре"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["check_status"] == "not_found" and body["checked_by"] == world.users["mio_region"].id
    assert (
        client.patch(
            f"/api/v1/documents/{created['id']}", headers=auth(world.users["mio_semey"]), json={"note": "x"}
        ).status_code
        == 404
    )


def test_attach_extra_evidence_to_document(client: TestClient, db: Session, world: World, bucket: str) -> None:
    obj = make_object(db, world.ust)
    created = client.post(
        f"/api/v1/objects/{obj.id}/documents", headers=auth(world.users["mio_ust"]), data={"doc_type": "psd"}
    ).json()
    response = client.post(
        f"/api/v1/documents/{created['id']}/evidence",
        headers=auth(world.users["mio_ust"]),
        files={"file": ("check.pdf", PDF_BYTES, "application/pdf")},
    )
    assert response.status_code == 201
    [item] = response.json()["evidence"]
    assert item["content_type"] == "application/pdf"


def test_evidence_access_is_scoped_and_hidden_from_receiving_bodies(
    client: TestClient, db: Session, world: World, bucket: str
) -> None:
    obj = make_object(db, world.ust)
    evidence_id = _post_document(client, world, obj.id)["evidence"][0]["id"]
    for key in ("mio_semey", "gask", "law"):
        response = client.get(f"/api/v1/evidence/{evidence_id}/content", headers=auth(world.users[key]))
        assert response.status_code == 404, key
    assert client.get(f"/api/v1/evidence/{evidence_id}", headers=auth(world.users["mio_region"])).status_code == 200
    assert client.get(f"/api/v1/evidence/{evidence_id}").status_code == 401


def test_inspection_uploads_photos_and_updates_actual_readiness(
    client: TestClient, db: Session, world: World, bucket: str
) -> None:
    obj = make_object(db, world.ust)
    headers = auth(world.users["mio_ust"])
    url = f"/api/v1/objects/{obj.id}/inspections"

    newer = client.post(
        url,
        headers=headers,
        data={"inspected_at": "2026-09-01", "readiness_pct": "45", "lat": "49.95", "lon": "82.61", "note": "каркас"},
        files=[("photos", ("a.png", PNG_BYTES, "image/png")), ("photos", ("b.png", PNG_BYTES + b"1", "image/png"))],
    )
    assert newer.status_code == 201, newer.text
    body = newer.json()
    assert len(body["evidence"]) == 2 and {e["kind"] for e in body["evidence"]} == {"photo"}
    assert body["lat"] == 49.95
    db.refresh(obj)
    assert obj.readiness_actual_pct == 45

    # An older inspection entered later must not overwrite the actual readiness.
    older = client.post(url, headers=headers, data={"inspected_at": "2026-06-01", "readiness_pct": "20"})
    assert older.status_code == 201
    db.refresh(obj)
    assert obj.readiness_actual_pct == 45

    detail = client.get(f"/api/v1/objects/{obj.id}", headers=headers).json()
    assert detail["readiness_actual_pct"] == 45
    assert [i["inspected_at"] for i in detail["inspections"]] == ["2026-09-01", "2026-06-01"]


def test_inspection_rejects_bad_input(client: TestClient, db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    headers = auth(world.users["mio_ust"])
    url = f"/api/v1/objects/{obj.id}/inspections"
    assert (
        client.post(url, headers=headers, data={"inspected_at": "2026-09-01", "readiness_pct": "150"}).status_code
        == 422
    )
    assert client.post(url, headers=headers, data={"inspected_at": str(date.today())}).status_code == 422
    bad_file = client.post(
        url,
        headers=headers,
        data={"inspected_at": "2026-09-01", "readiness_pct": "10"},
        files={"photos": ("a.pdf", PDF_BYTES, "application/pdf")},
    )
    assert bad_file.status_code == 415
