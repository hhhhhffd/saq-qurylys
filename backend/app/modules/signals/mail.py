"""Optional e-mail delivery. Enabled only when SMTP_HOST is set; failures are logged, never raised:
the in-app record is the source of truth and a mail outage must not undo a business action."""

import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.config import get_settings

logger = logging.getLogger(__name__)

SMTP_TIMEOUT_S = 15
SMTPS_PORT = 465


def smtp_enabled() -> bool:
    settings = get_settings()
    return bool(settings.smtp_host and settings.smtp_from)


def send_email(
    recipients: list[str], subject: str, body: str, attachment: tuple[str, bytes, str] | None = None
) -> bool:
    """Send a plain-text message, optionally with one attachment (filename, bytes, MIME type).
    Returns whether the message was handed to the SMTP server."""
    settings = get_settings()
    if not smtp_enabled() or not recipients:
        return False
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = ", ".join(recipients)
    message["Subject"] = subject
    message.set_content(body)
    if attachment is not None:
        filename, data, mime_type = attachment
        maintype, _, subtype = mime_type.partition("/")
        message.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)
    try:
        context = ssl.create_default_context()
        if settings.smtp_port == SMTPS_PORT:
            server: smtplib.SMTP = smtplib.SMTP_SSL(
                settings.smtp_host, settings.smtp_port, timeout=SMTP_TIMEOUT_S, context=context
            )
        else:
            server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=SMTP_TIMEOUT_S)
        with server:
            server.ehlo()
            if settings.smtp_port != SMTPS_PORT and server.has_extn("starttls"):
                server.starttls(context=context)
                server.ehlo()
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(message)
    except (OSError, smtplib.SMTPException):
        logger.exception("Could not send e-mail %r to %s", subject, recipients)
        return False
    return True
