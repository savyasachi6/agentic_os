"""
Telegram and Slack webhook bridge for phone-driven development.
Allows interacting with the agent via chat platforms.
"""
import json
import urllib.request
from typing import Optional


class TelegramBridge:
    def __init__(self, token: str):
        self.token = token
        self.base_url = f"https://api.telegram.org/bot{token}"

    def send(self, chat_id: str, text: str) -> bool:
        """Send a message via Telegram Bot API."""
        url = f"{self.base_url}/sendMessage"
        data = json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as response:
                return response.status == 200
        except Exception as e:
            print(f"Telegram send error: {e}")
            return False

    def poll_updates(self, offset: Optional[int] = None) -> list:
        """Poll for new messages (getUpdates)."""
        url = f"{self.base_url}/getUpdates"
        if offset:
            url += f"?offset={offset}"
        try:
            with urllib.request.urlopen(url) as response:
                data = json.loads(response.read().decode())
                return data.get("result", [])
        except Exception as e:
            print(f"Telegram poll error: {e}")
            return []


class SlackBridge:
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send(self, text: str) -> bool:
        """Send a message to a Slack channel via Incoming Webhook."""
        data = json.dumps({"text": text}).encode("utf-8")
        req = urllib.request.Request(self.webhook_url, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as response:
                return response.status == 200
        except Exception as e:
            print(f"Slack send error: {e}")
            return False


class ChatRouter:
    """
    Routes incoming chat messages to the agent and dispatches responses.
    """
    def __init__(self, agent_loop):
        self.agent = agent_loop

    def handle_message(self, platform: str, user_id: str, text: str, reply_fn):
        """
        Process an incoming message through the agent loop.
        """
        print(f"[{platform}] Message from {user_id}: {text}")
        # Run agent turn
        response = self.agent.run_turn(text)
        # Dispatch back
        reply_fn(response)
