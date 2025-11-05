import logging
import smtplib
import ssl
from email.message import EmailMessage

from config import get_settings


def send_email(
    recipient_emails: list[str],
    subject: str,
    html_content: str,
):
    """Sends an email using Office365 SMTP, based on provided implementation details."""
    settings = get_settings()
    if not settings.smtp_sender_email or not settings.smtp_password:
        logging.error("SMTP credentials are not configured. Cannot send email.")
        # In a real app, you might want to raise an exception here
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_sender_email
    msg["To"] = ", ".join(recipient_emails)
    msg.set_content("Please enable HTML to view this email.")  # Fallback for non-HTML clients
    msg.add_alternative(html_content, subtype="html")

    context = ssl.create_default_context()

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
            smtp.starttls(context=context)
            smtp.login(settings.smtp_sender_email, settings.smtp_password)
            smtp.send_message(msg)
        logging.info(f"Email sent to {', '.join(recipient_emails)}")
    except Exception as e:
        logging.exception(f"Failed to send email: {e}")
        # Depending on requirements, you might want to re-raise or handle this
