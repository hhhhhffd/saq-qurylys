from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, Index, LargeBinary, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, enum_type, fk
from app.models.enums import EvidenceKind, LockMode


class Evidence(IdMixin, Base):
    """Append-only: UPDATE and DELETE are rejected by a database trigger."""

    __tablename__ = "evidence"
    __table_args__ = (
        UniqueConstraint("bucket", "s3_key"),
        CheckConstraint(
            "num_nonnulls(ad_post_id, document_id, inspection_id, signal_card_id) = 1",
            name="exactly_one_owner",
        ),
        Index("ix_evidence_sha256", "sha256"),
    )

    kind: Mapped[EvidenceKind] = mapped_column(enum_type(EvidenceKind, "evidence_kind"))
    bucket: Mapped[str] = mapped_column(String(255))
    s3_key: Mapped[str] = mapped_column(String(1024))
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    content_type: Mapped[str] = mapped_column(String(255))
    captured_at: Mapped[datetime] = mapped_column(server_default=func.now())
    source_url: Mapped[str | None] = mapped_column(Text)
    retention_until: Mapped[datetime]
    lock_mode: Mapped[LockMode] = mapped_column(enum_type(LockMode, "lock_mode"))
    tsa_token: Mapped[bytes | None] = mapped_column(LargeBinary)
    ad_post_id: Mapped[int | None] = fk("ad_post.id", nullable=True, index=True)
    document_id: Mapped[int | None] = fk("document.id", nullable=True, index=True)
    inspection_id: Mapped[int | None] = fk("inspection.id", nullable=True, index=True)
    signal_card_id: Mapped[int | None] = fk("signal_card.id", nullable=True, index=True)
    created_by: Mapped[int | None] = fk("app_user.id", nullable=True)

    @property
    def has_tsa_token(self) -> bool:
        return self.tsa_token is not None
