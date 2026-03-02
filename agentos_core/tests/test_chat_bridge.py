import pytest
import json
from unittest.mock import MagicMock, patch
from devops_auto.chat_bridge import TelegramBridge, SlackBridge, ChatRouter

@patch("urllib.request.urlopen")
def test_telegram_bridge_send_success(mock_urlopen):
    mock_response = MagicMock()
    mock_response.status = 200
    mock_urlopen.return_value.__enter__.return_value = mock_response
    
    bridge = TelegramBridge(token="test_token")
    result = bridge.send(chat_id="123", text="Hello from Agent OS")
    
    assert result is True
    # Verify request
    args, kwargs = mock_urlopen.call_args
    req = args[0]
    assert req.full_url == "https://api.telegram.org/bottest_token/sendMessage"
    payload = json.loads(req.data.decode("utf-8"))
    assert payload["chat_id"] == "123"
    assert payload["text"] == "Hello from Agent OS"

@patch("urllib.request.urlopen")
def test_telegram_bridge_poll_updates(mock_urlopen):
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({
        "ok": True,
        "result": [{"message": {"text": "Hello Bot", "chat": {"id": "123"}}}]
    }).encode("utf-8")
    mock_urlopen.return_value.__enter__.return_value = mock_response
    
    bridge = TelegramBridge(token="test_token")
    updates = bridge.poll_updates(offset=100)
    
    assert len(updates) == 1
    assert updates[0]["message"]["text"] == "Hello Bot"
    
    args, kwargs = mock_urlopen.call_args
    url = args[0]
    assert "offset=100" in url

@patch("urllib.request.urlopen")
def test_slack_bridge_send_success(mock_urlopen):
    mock_response = MagicMock()
    mock_response.status = 200
    mock_urlopen.return_value.__enter__.return_value = mock_response
    
    bridge = SlackBridge(webhook_url="https://hooks.slack.com/services/abc")
    result = bridge.send(text="Slack alert")
    
    assert result is True
    args, kwargs = mock_urlopen.call_args
    req = args[0]
    payload = json.loads(req.data.decode("utf-8"))
    assert payload["text"] == "Slack alert"

def test_chat_router_dispatch():
    mock_agent = MagicMock()
    mock_agent.run_turn.return_value = "Agent response"
    
    mock_reply = MagicMock()
    
    router = ChatRouter(agent_loop=mock_agent)
    router.handle_message(platform="telegram", user_id="user1", text="Who are you?", reply_fn=mock_reply)
    
    mock_agent.run_turn.assert_called_once_with("Who are you?")
    mock_reply.assert_called_once_with("Agent response")
