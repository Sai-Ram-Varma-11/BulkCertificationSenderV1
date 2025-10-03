import os
import smtplib
from email.message import EmailMessage
from typing import Optional


def send_certificate_email(to_email: str, subject: str, body: str, attachment_path: Optional[str]) -> bool:
	"""Send email via SMTP using ENV: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM, SMTP_TLS=1"""
	try:
		host = os.getenv("SMTP_HOST", "smtp.gmail.com")
		port = int(os.getenv("SMTP_PORT", "587"))
		user = os.getenv("SMTP_USER")
		pwd = os.getenv("SMTP_PASS")
		mail_from = os.getenv("SMTP_FROM", user or "noreply@example.com")
		use_tls = os.getenv("SMTP_TLS", "1") == "1"

		msg = EmailMessage()
		msg["From"] = mail_from
		msg["To"] = to_email
		msg["Subject"] = subject
		msg.set_content(body)

		if attachment_path:
			with open(attachment_path, "rb") as f:
				data = f.read()
				msg.add_attachment(data, maintype="image", subtype="png", filename=os.path.basename(attachment_path))

		s = smtplib.SMTP(host, port, timeout=20)
		if use_tls:
			s.starttls()
		if user and pwd:
			s.login(user, pwd)
		s.send_message(msg)
		s.quit()
		return True
	except Exception:
		return False