from datetime import date, datetime
from typing import Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.enums import AssignmentStatus, Role, Zone
from app.schemas import ORMModel


def _stripped(value: str | None) -> str | None:
    return value.strip() if value is not None else None


class AssignmentObject(ORMModel):
    id: int
    name: str
    code: str | None
    zone: Zone | None


class AssignmentOut(BaseModel):
    id: int
    object: AssignmentObject
    author_id: int
    author_name: str
    assignee_id: int
    assignee_name: str
    task: str
    due_date: date
    status: AssignmentStatus
    is_overdue: bool
    days_overdue: int
    result: str | None
    completed_at: datetime | None
    created_at: datetime


class AssigneeOut(ORMModel):
    id: int
    full_name: str
    role: Role


class AssignmentCreate(BaseModel):
    assignee_id: int
    task: str = Field(min_length=1, max_length=2000)
    due_date: date

    _strip_task = field_validator("task")(_stripped)

    @model_validator(mode="after")
    def task_not_blank(self) -> Self:
        if not self.task:
            raise ValueError("Текст поручения не может быть пустым")
        return self


class AssignmentPatch(BaseModel):
    status: Literal["done", "cancelled"] | None = None
    result: str | None = Field(default=None, max_length=5000)
    task: str | None = Field(default=None, min_length=1, max_length=2000)
    due_date: date | None = None
    assignee_id: int | None = None

    _strip = field_validator("result", "task")(_stripped)

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if self.status == "done" and not self.result:
            raise ValueError("Опишите результат проверки")
        if self.status != "done" and self.result is not None:
            raise ValueError("Результат указывается только при выполнении")
        if self.task == "":
            raise ValueError("Текст поручения не может быть пустым")
        return self
