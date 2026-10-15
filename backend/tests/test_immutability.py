from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import audit
from app.config import get_settings
from app.models import Document, Evidence, RiskFactorChange
from app.models.enums import DocType, EvidenceKind, LockMode
from tests.conftest import World, make_object


def _evidence(db: Session, world: World) -> Evidence:
    obj = make_object(db, world.ust)
    document = Document(object_id=obj.id, doc_type=DocType.psd)
    db.add(document)
    db.flush()
    evidence = Evidence(
        kind=EvidenceKind.document_scan,
        bucket=get_settings().s3_bucket_evidence,
        s3_key="test/immutability",
        sha256="0" * 64,
        size_bytes=1,
        content_type="application/pdf",
        retention_until=datetime.now(UTC),
        lock_mode=LockMode.GOVERNANCE,
        document_id=document.id,
    )
    db.add(evidence)
    db.flush()
    return evidence


def _assert_append_only(db: Session, statement: str, **params: object) -> None:
    with pytest.raises(IntegrityError, match="append-only"), db.begin_nested():
        db.execute(text(statement), params)


def test_evidence_cannot_be_updated_or_deleted(db: Session, world: World) -> None:
    evidence = _evidence(db, world)
    _assert_append_only(db, "UPDATE evidence SET size_bytes = 2 WHERE id = :id", id=evidence.id)
    _assert_append_only(db, "UPDATE evidence SET sha256 = repeat('f', 64) WHERE id = :id", id=evidence.id)
    _assert_append_only(db, "DELETE FROM evidence WHERE id = :id", id=evidence.id)
    _assert_append_only(db, "TRUNCATE evidence CASCADE")


def test_orm_changes_to_evidence_are_rejected(db: Session, world: World) -> None:
    evidence = _evidence(db, world)
    evidence.size_bytes = 99
    with pytest.raises(IntegrityError, match="append-only"), db.begin_nested():
        db.flush()


def test_audit_log_is_append_only(db: Session, world: World) -> None:
    entry = audit.record(db, world.users["admin"], "test.action", "test", 1, None, {"a": 1})
    _assert_append_only(db, "UPDATE audit_log SET action = 'forged' WHERE id = :id", id=entry.id)
    _assert_append_only(db, "DELETE FROM audit_log WHERE id = :id", id=entry.id)


def test_risk_factor_history_is_append_only(db: Session, world: World) -> None:
    change = RiskFactorChange(code="no_permit", old_weight=40, new_weight=45, old_active=True, new_active=True)
    db.add(change)
    db.flush()
    _assert_append_only(db, "UPDATE risk_factor_change SET new_weight = 0 WHERE id = :id", id=change.id)
    _assert_append_only(db, "DELETE FROM risk_factor_change WHERE id = :id", id=change.id)


def test_evidence_requires_exactly_one_owner(db: Session, world: World) -> None:
    evidence = _evidence(db, world)
    db.add(
        Evidence(
            kind=EvidenceKind.photo,
            bucket="b",
            s3_key="no-owner",
            sha256="1" * 64,
            size_bytes=1,
            content_type="image/png",
            retention_until=evidence.retention_until,
            lock_mode=LockMode.GOVERNANCE,
        )
    )
    with pytest.raises(IntegrityError, match="exactly_one_owner"), db.begin_nested():
        db.flush()
