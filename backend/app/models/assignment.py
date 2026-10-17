from datetime import date, datetime

from sqlalchemy import Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin, enum_type, fk
from app.models.enums import AssignmentStatus


class Assignment(IdMixin, TimestampMixin, Base):
    """A manager asks an employee to check an object by a calendar date."""

    __tablename__ = "assignment"
    __table_args__ = (
        Index("ix_assignment_assignee_status", "assignee_id", "status"),
        Index("ix_assignment_object_id", "object_id"),
    )

    object_id: Mapped[int] = fk("construction_object.id")
    author_id: Mapped[int] = fk("app_user.id")
    assignee_id: Mapped[int] = fk("app_user.id")
    task: Mapped[str] = mapped_column(String(2000))
    due_date: Mapped[date]
    status: Mapped[AssignmentStatus] = mapped_column(
        enum_type(AssignmentStatus, "assignment_status"), server_default=AssignmentStatus.open.value
    )
    result: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None]
