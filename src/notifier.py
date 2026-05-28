"""
Email notifications via Gmail SMTP with TLS.
Credentials are never logged — passwords masked as *****.
"""
import logging
import smtplib
import traceback
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

log = logging.getLogger(__name__)


def _mask(value: str) -> str:
    """Mask a sensitive string for logging."""
    if not value:
        return "*****"
    return value[:2] + "*****" if len(value) > 2 else "*****"


def _build_smtp_connection(config: dict, env: dict) -> smtplib.SMTP:
    """Create and authenticate an SMTP connection."""
    email_cfg = config.get("email", {})
    smtp_host = email_cfg.get("smtp_host", "smtp.gmail.com")
    smtp_port = int(email_cfg.get("smtp_port", 587))
    sender = env.get("EMAIL_SENDER", "")
    password = env.get("GMAIL_APP_PASSWORD", "")

    log.info(f"Connecting to SMTP {smtp_host}:{smtp_port} as {sender} (password: {_mask(password)})")
    smtp = smtplib.SMTP(smtp_host, smtp_port, timeout=30)
    smtp.ehlo()
    smtp.starttls()
    smtp.ehlo()
    smtp.login(sender, password)
    log.info("SMTP authenticated successfully.")
    return smtp


def send_report_email(
    html_body: str,
    attachments: list[Path],
    config: dict,
    env: dict,
) -> None:
    """Send the weekly report email with HTML body and file attachments."""
    email_cfg = config.get("email", {})
    sender = env.get("EMAIL_SENDER", "")
    recipients = [r.strip() for r in env.get("EMAIL_RECIPIENT", "").split(",") if r.strip()]

    if not sender or not recipients:
        log.error("EMAIL_SENDER or EMAIL_RECIPIENT not set — cannot send email.")
        return

    msg = MIMEMultipart("mixed")
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    # Subject is set by caller via the template; use generic fallback here
    msg["Subject"] = email_cfg.get("subject", "AskLivermore Watchlist Report")

    # HTML body
    html_part = MIMEMultipart("alternative")
    html_part.attach(MIMEText(html_body, "html", "utf-8"))
    msg.attach(html_part)

    # Attachments
    for attach_path in attachments:
        if not attach_path.exists():
            log.warning(f"Attachment not found, skipping: {attach_path}")
            continue
        try:
            with open(attach_path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f"attachment; filename={attach_path.name}",
            )
            msg.attach(part)
            log.debug(f"Attached: {attach_path.name}")
        except Exception as e:
            log.warning(f"Failed to attach {attach_path}: {e}")

    try:
        smtp = _build_smtp_connection(config, env)
        smtp.sendmail(sender, recipients, msg.as_string())
        smtp.quit()
        log.info(f"Report email sent to {', '.join(recipients)}.")
    except Exception as e:
        log.error(f"Failed to send report email: {e}")
        raise


def send_alert_email(
    subject: str,
    body: str,
    config: dict,
    env: dict,
) -> None:
    """Send a plain-text alert email (used for pipeline errors)."""
    email_cfg = config.get("email", {})
    sender = env.get("EMAIL_SENDER", "")
    recipients = [r.strip() for r in env.get("EMAIL_RECIPIENT", "").split(",") if r.strip()]

    if not sender or not recipients:
        log.error("EMAIL_SENDER or EMAIL_RECIPIENT not set — cannot send alert email.")
        return

    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = f"[AskLivermore Alert] {subject}"
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        smtp = _build_smtp_connection(config, env)
        smtp.sendmail(sender, recipients, msg.as_string())
        smtp.quit()
        log.info(f"Alert email sent: {subject}")
    except Exception as e:
        log.error(f"Failed to send alert email '{subject}': {e}")


def send_cookies_expired_alert(config: dict, env: dict) -> None:
    """Send a specific alert when AskLivermore cookies have expired."""
    subject = "AskLivermore Cookies Expired — Action Required"
    body = (
        "The saved session cookies for AskLivermore have expired.\n\n"
        "To fix this:\n"
        "1. Open a terminal on your Mac\n"
        "2. Run: cd /Users/dodomac/Desktop/askdodo && python3 login_setup.py\n"
        "3. A browser window will open — log in with your Google account\n"
        "4. Press ENTER in the terminal when done\n\n"
        "The weekly bot will then work automatically again next Saturday.\n\n"
        "— AskLivermore Auto-Funnel"
    )
    send_alert_email(subject, body, config, env)
