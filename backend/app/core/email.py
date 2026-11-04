"""
Production Real-Time Email Delivery Service.

Sends transactional emails (such as 6-digit verification OTPs) using standard
SMTP with STARTTLS or SSL. Asynchronous execution via asyncio.to_thread ensures
FastAPI event loops are never blocked.
"""
import asyncio
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("app.core.email")


def _build_otp_html(otp: str, user_name: str | None = None) -> str:
    greeting = f"Hello {user_name}," if user_name else "Hello,"
    spaced_otp = " ".join(list(otp))
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Password Reset OTP</title>
</head>
<body style="margin: 0; padding: 0; background-color: #0f172a; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #f8fafc;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color: #0f172a; padding: 40px 20px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" style="max-width: 520px; background-color: #1e293b; border-radius: 16px; border: 1px solid #334155; overflow: hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.5);" cellspacing="0" cellpadding="0" border="0">
          <!-- Header Banner -->
          <tr>
            <td style="background: linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%); padding: 32px 30px; text-align: center;">
              <h1 style="margin: 0; color: #ffffff; font-size: 24px; font-weight: 800; letter-spacing: -0.5px;">Welfog AI Engine</h1>
              <p style="margin: 6px 0 0; color: #e0e7ff; font-size: 13px; font-weight: 500;">Secure Password Verification</p>
            </td>
          </tr>
          
          <!-- Content Body -->
          <tr>
            <td style="padding: 36px 32px;">
              <p style="margin: 0 0 16px; font-size: 15px; color: #cbd5e1; line-height: 1.5;">{greeting}</p>
              <p style="margin: 0 0 24px; font-size: 14px; color: #94a3b8; line-height: 1.6;">
                We received a request to reset your password. Use the verification code below to complete the reset process.
              </p>
              
              <!-- OTP Box -->
              <div style="background-color: #0f172a; border: 1px dashed #7c3aed; border-radius: 12px; padding: 24px 20px; text-align: center; margin-bottom: 24px;">
                <span style="font-family: 'SF Mono', Consolas, Monaco, monospace; font-size: 34px; font-weight: 700; letter-spacing: 8px; color: #a78bfa; display: inline-block;">
                  {spaced_otp}
                </span>
                <p style="margin: 10px 0 0; font-size: 12px; color: #64748b; text-transform: uppercase; letter-spacing: 1px;">
                  Expires in 5 minutes &bull; 5 attempts maximum
                </p>
              </div>

              <p style="margin: 0 0 12px; font-size: 13px; color: #94a3b8; line-height: 1.5;">
                &bull; Never share this code with anyone.<br>
                &bull; If you did not make this request, you can safely ignore this email.
              </p>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background-color: #0f172a; padding: 20px 32px; text-align: center; border-top: 1px solid #334155;">
              <p style="margin: 0; font-size: 12px; color: #64748b;">
                &copy; 2026 Welfog AI Personalization. All rights reserved.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _send_smtp_sync(to_email: str, subject: str, text_content: str, html_content: str) -> None:
    host = settings.SMTP_HOST.strip()
    port = settings.SMTP_PORT
    user = settings.SMTP_USER.strip()
    password = settings.SMTP_PASSWORD.strip()

    # If sending through Gmail and from_email is default 'noreply@welfog.com',
    # use authenticated user email to prevent Gmail 553/550 sender rejection.
    from_email = settings.SMTP_FROM_EMAIL.strip()
    if not from_email or (from_email == "noreply@welfog.com" and user):
        from_email = user
    from_name = settings.SMTP_FROM_NAME.strip()
    timeout = settings.SMTP_TIMEOUT_SECONDS

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{from_email}>" if from_name else from_email
    msg["To"] = to_email

    msg.attach(MIMEText(text_content, "plain", "utf-8"))
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    if settings.SMTP_USE_SSL or port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=timeout) as server:
            if user and password:
                server.login(user, password)
            server.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=timeout) as server:
            server.ehlo()
            if settings.SMTP_USE_TLS:
                server.starttls()
                server.ehlo()
            if user and password:
                server.login(user, password)
            server.send_message(msg)


async def send_otp_email(to_email: str, otp: str, user_name: str | None = None) -> bool:
    """
    Deliver 6-digit OTP code to user's registered email via configured SMTP.
    Returns True if sent, False if SMTP is unconfigured or encountered an error.
    """
    host = settings.SMTP_HOST.strip()
    user = settings.SMTP_USER.strip()
    password = settings.SMTP_PASSWORD.strip()

    if not host or not user or not password:
        logger.warning(
            "smtp_unconfigured_otp_email_skipped",
            recipient=to_email,
            hint="Set SMTP_USER and SMTP_PASSWORD in backend/.env for real email delivery via Gmail.",
        )
        # Development fallback log so local testing is never blocked
        logger.info(
            "dev_otp_fallback_code",
            recipient=to_email,
            otp=otp,
            info="Enter this code in Flutter dialog or configure SMTP in backend/.env for real Gmail delivery.",
        )
        return False

    subject = f"{otp} is your Welfog AI verification code"
    text_content = (
        f"Your verification code is: {otp}\n\n"
        "This code will expire in 5 minutes. Do not share this code with anyone.\n"
        "If you did not request this password reset, please ignore this email."
    )
    html_content = _build_otp_html(otp, user_name)

    try:
        await asyncio.to_thread(_send_smtp_sync, to_email, subject, text_content, html_content)
        logger.info("otp_email_dispatched_successfully", recipient=to_email)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("otp_email_delivery_failed", recipient=to_email, error=str(exc))
        # Log dev fallback in case of delivery failure
        logger.info("dev_otp_fallback_code_after_failure", recipient=to_email, otp=otp)
        return False

