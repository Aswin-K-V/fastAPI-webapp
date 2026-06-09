from email.message import EmailMessage
import logging

import aiosmtplib
from fastapi.templating import Jinja2Templates

from config import settings

templates = Jinja2Templates(directory="templates")
logger = logging.getLogger(__name__)


async def send_email(
    to_email: str,
    subject: str,
    plain_text: str,
    html_content: str | None = None,
) -> None:
    message = EmailMessage()
    message["From"] = settings.mail_from
    message["To"] = to_email
    message["Subject"] = subject

    message.set_content(plain_text)

    if html_content:
        message.add_alternative(html_content, subtype="html")

    mail_username = settings.mail_username.strip()
    mail_password = settings.mail_password.get_secret_value().strip()
    if bool(mail_username) != bool(mail_password):
        raise RuntimeError(
            "MAIL_USERNAME and MAIL_PASSWORD must both be set for SMTP authentication"
        )

    await aiosmtplib.send(
        message,
        hostname=settings.mail_server,
        port=settings.mail_port,
        username=mail_username or None,
        password=mail_password or None,
        start_tls=settings.mail_use_tls,
    )


async def send_password_reset_email(to_email: str, username: str, token: str) -> None:
    reset_url = f"{settings.frontend_url}/reset-password?token={token}"

    template = templates.env.get_template("email/password_reset.html")
    html_content = template.render(reset_url=reset_url, username=username)

    plain_text = f"""Hi {username},

You requested to reset your password. Click the link below to set a new password:

{reset_url}

This link will expire in 1 hour.

If you didn't request this, you can safely ignore this email.

Best regards,
The FastAPI Blog Team
"""

    await send_email(
        to_email=to_email,
        subject="Reset Your Password - FastAPI Blog",
        plain_text=plain_text,
        html_content=html_content,
    )


async def send_password_reset_email_safely(
    to_email: str, username: str, token: str
) -> None:
    try:
        await send_password_reset_email(to_email, username, token)
    except (RuntimeError, aiosmtplib.SMTPException):
        logger.exception(
            "Failed to send password reset email via %s:%s from %s to %s",
            settings.mail_server,
            settings.mail_port,
            settings.mail_from,
            to_email,
        )
