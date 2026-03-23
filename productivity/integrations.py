"""
Connector stubs for external services (Email, Calendar, Web).
"""
from typing import List, Optional


from agent_config import email_settings
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

class EmailConnector:
    """IMAP/SMTP integration using system settings."""
    def list_emails(self, folder: str = "INBOX", limit: int = 10) -> List[dict]:
        # Placeholder for IMAP integration
        return [{"subject": "Welcome to Agent OS", "from": "admin@agentos.ai", "body": "..."}]

    def send_email(self, to: str, subject: str, body: str) -> bool:
        """Sends an email using configured SMTP settings."""
        if not email_settings.smtp_user or not email_settings.smtp_password:
            print(f"[EmailConnector] SMTP credentials missing. Mocking send to {to}.")
            return True
            
        try:
            msg = MIMEMultipart()
            msg['From'] = email_settings.email_from
            msg['To'] = to
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))

            server = smtplib.SMTP(email_settings.smtp_host, email_settings.smtp_port)
            server.starttls()
            server.login(email_settings.smtp_user, email_settings.smtp_password)
            server.send_message(msg)
            server.quit()
            print(f"[EmailConnector] Email sent successfully to {to}")
            return True
        except Exception as e:
            print(f"[EmailConnector] Error sending email: {e}")
            return False


class CalendarConnector:
    """Stub for Google/Outlook Calendar integration."""
    def list_events(self, start_time=None, end_time=None) -> List[dict]:
        return [{"title": "Agent Sync", "time": "10:00 AM", "duration": "30m"}]

    def create_event(self, title: str, start_time: str, end_time: str) -> bool:
        print(f"Mock event created: {title}")
        return True


class WebSearchConnector:
    """Stub for DuckDuckGo/SerpAPI integration."""
    def search(self, query: str) -> List[dict]:
        return [{"title": "Agentic OS Docs", "link": "https://docs.agentos.ai", "snippet": "..."}]
