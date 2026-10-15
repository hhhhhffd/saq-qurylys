"""SMTP delivery: enabled only by configuration, failures are logged and reported, never raised."""

import smtplib
from email.message import EmailMessage
from typing import Any

import pytest

from app.config import get_settings
from app.modules.signals import mail


class FakeSMTP:
    instances: list["FakeSMTP"] = []  # noqa: RUF012
    fail_on_send = False

    def __init__(self, host: str, port: int, timeout: int | None = None, **kwargs: Any) -> None:
        self.host, self.port, self.timeout = host, port, timeout
        self.started_tls = False
        self.logged_in: tuple[str, str] | None = None
        self.sent: list[EmailMessage] = []
        FakeSMTP.instances.append(self)

    def __enter__(self) -> "FakeSMTP":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def ehlo(self) -> None:
        return None

    def has_extn(self, name: str) -> bool:
        return name == "starttls"

    def starttls(self, **kwargs: Any) -> None:
        self.started_tls = True

    def login(self, user: str, password: str) -> None:
        self.logged_in = (user, password)

    def send_message(self, message: EmailMessage) -> None:
        if FakeSMTP.fail_on_send:
            raise smtplib.SMTPException("relay denied")
        self.sent.append(message)


@pytest.fixture
def smtp(monkeypatch: pytest.MonkeyPatch) -> type[FakeSMTP]:
    FakeSMTP.instances = []
    FakeSMTP.fail_on_send = False
    settings = get_settings()
    for name, value in (
        ("smtp_host", "smtp.example.kz"),
        ("smtp_port", 587),
        ("smtp_user", "robot"),
        ("smtp_password", "secret"),
        ("smtp_from", "saq@example.kz"),
    ):
        monkeypatch.setattr(settings, name, value)
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    return FakeSMTP


def test_disabled_without_a_host() -> None:
    assert mail.smtp_enabled() is False
    assert mail.send_email(["a@example.kz"], "s", "b") is False


def test_message_with_a_pdf_attachment(smtp: type[FakeSMTP]) -> None:
    assert mail.smtp_enabled() is True
    sent = mail.send_email(
        ["a@example.kz", "b@example.kz"], "Тема", "Текст", ("card.pdf", b"%PDF-1.7 data", "application/pdf")
    )

    assert sent is True
    [server] = smtp.instances
    assert (server.host, server.port, server.started_tls, server.logged_in) == (
        "smtp.example.kz",
        587,
        True,
        ("robot", "secret"),
    )
    [message] = server.sent
    assert (message["From"], message["To"], message["Subject"]) == (
        "saq@example.kz",
        "a@example.kz, b@example.kz",
        "Тема",
    )
    [attachment] = list(message.iter_attachments())
    assert attachment.get_filename() == "card.pdf"
    assert attachment.get_content_type() == "application/pdf"
    assert attachment.get_payload(decode=True) == b"%PDF-1.7 data"


def test_no_recipients_means_no_connection(smtp: type[FakeSMTP]) -> None:
    assert mail.send_email([], "s", "b") is False
    assert smtp.instances == []


def test_relay_failure_is_reported_not_raised(smtp: type[FakeSMTP], caplog: pytest.LogCaptureFixture) -> None:
    smtp.fail_on_send = True
    assert mail.send_email(["a@example.kz"], "s", "b") is False
    assert "Could not send e-mail" in caplog.text


def test_connection_failure_is_reported_not_raised(monkeypatch: pytest.MonkeyPatch, smtp: type[FakeSMTP]) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        raise ConnectionRefusedError("down")

    monkeypatch.setattr(smtplib, "SMTP", refuse)
    assert mail.send_email(["a@example.kz"], "s", "b") is False
