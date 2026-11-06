import smtplib
from email.message import EmailMessage

import structlog

from app.core.config import get_settings

log = structlog.get_logger("proptwin.email")


def send_email(to: str, subject: str, body: str) -> str:
    """Returns 'sent' or 'not_configured'. Callers never treat an unconfigured mailer as delivered."""
    settings = get_settings()
    if not settings.smtp_host:
        log.warning("email_not_configured", subject=subject)
        if not settings.is_production:
            # Local development has no mailbox, so the link is only ever printed to the developer's console.
            print(f"[dev email] to={to} subject={subject}\n{body}", flush=True)
        return "not_configured"
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
        smtp.starttls()
        if settings.smtp_username and settings.smtp_password:
            smtp.login(settings.smtp_username, settings.smtp_password.get_secret_value())
        smtp.send_message(message)
    return "sent"
