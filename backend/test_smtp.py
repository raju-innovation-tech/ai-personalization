"""
CLI tool to test Gmail / SMTP configuration and verify real email delivery.
Usage:
    docker exec aip_backend python test_smtp.py [recipient@example.com]
"""
import sys
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from app.core.config import settings

def test_smtp(recipient: str | None = None):
    print("=" * 60)
    print("🔍 Testing Real-time Gmail / SMTP Configuration")
    print("=" * 60)

    host = settings.SMTP_HOST.strip()
    port = settings.SMTP_PORT
    user = settings.SMTP_USER.strip()
    password = settings.SMTP_PASSWORD.strip()
    from_name = settings.SMTP_FROM_NAME.strip()
    from_email = settings.SMTP_FROM_EMAIL.strip() or user

    print(f"SMTP Host       : {host}")
    print(f"SMTP Port       : {port}")
    print(f"SMTP User       : {user or '(NOT SET - Please configure in backend/.env)'}")
    print(f"SMTP Password   : {'*' * len(password) if password else '(NOT SET - Please configure in backend/.env)'}")
    print(f"From Email      : {from_email or '(NOT SET)'}")
    print(f"Use TLS         : {settings.SMTP_USE_TLS}")
    print(f"Use SSL         : {settings.SMTP_USE_SSL}")
    print("-" * 60)

    if not host or not user or not password:
        print("❌ SMTP credentials are not fully configured in backend/.env!")
        print("\nTo fix this for Gmail:")
        print("1. Go to your Google Account -> Security -> 2-Step Verification.")
        print("2. At the bottom, go to 'App passwords'.")
        print("3. Create an app password named 'Welfog Engine'.")
        print("4. Copy the 16-character password into backend/.env:")
        print("   SMTP_USER=your_email@gmail.com")
        print("   SMTP_PASSWORD=xxxx xxxx xxxx xxxx")
        print("5. Restart container: docker restart aip_backend\n")
        return

    to_addr = recipient or user
    print(f"Attempting to send test email to: {to_addr} ...")

    msg = MIMEMultipart()
    msg["Subject"] = "🧪 Welfog AI Engine - SMTP Test Verification"
    msg["From"] = f"{from_name} <{user}>"
    msg["To"] = to_addr

    body = (
        "Hello!\n\n"
        "This is a test email from Welfog AI Personalization Engine.\n"
        "If you are reading this, your Gmail SMTP configuration is working perfectly!\n\n"
        "All staff members (Super Admin, Admin, Manager, Analyst, Viewer) can now receive real OTPs.\n"
    )
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        if settings.SMTP_USE_SSL or port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=10) as server:
                server.login(user, password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=10) as server:
                server.ehlo()
                if settings.SMTP_USE_TLS:
                    server.starttls()
                    server.ehlo()
                server.login(user, password)
                server.send_message(msg)

        print(f"✅ SUCCESS! Test email dispatched successfully to {to_addr}.")
        print("🎉 Check your Gmail inbox (and Spam/Promotions folder).")
    except smtplib.SMTPAuthenticationError as e:
        print(f"❌ Authentication Failed: {e}")
        print("👉 Make sure you are using a 16-character 'Google App Password', NOT your standard Gmail password!")
    except Exception as e:
        print(f"❌ Error sending email: {e}")

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else None
    test_smtp(target)

