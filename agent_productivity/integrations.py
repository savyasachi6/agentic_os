"""
Connector stubs for external services (Email, Calendar, Web).
"""
from typing import List, Optional


class EmailConnector:
    """Stub for IMAP/SMTP integration."""
    def list_emails(self, folder: str = "INBOX", limit: int = 10) -> List[dict]:
        return [{"subject": "Welcome to Agent OS", "from": "admin@agentos.ai", "body": "..."}]

    def send_email(self, to: str, subject: str, body: str) -> bool:
        print(f"Mock email sent to {to}: {subject}")
        return True


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
