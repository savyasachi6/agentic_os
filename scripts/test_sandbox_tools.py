import requests
import jwt
from datetime import datetime, timedelta, timezone
import sys
import os

# Add the project root to sys.path to import core
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from agent_core.config import settings
except ImportError:
    print("Error: Could not import agent_core.config. Make sure you're running from the project root.")
    sys.exit(1)

def generate_test_token():
    """Generate a JWT for testing the sandbox worker."""
    payload = {
        "sub": "test-user",
        "scopes": ["tool:low", "tool:high"],
        "exp": datetime.now(timezone.utc) + timedelta(minutes=30)
    }
    return jwt.encode(payload, settings.admin_secret, algorithm=settings.jwt_algorithm)

def test_sandbox_tools():
    # Use the service name if running from another container, or localhost if from host
    # Since we are likely running this from the host (developer's machine), use localhost.
    # The tools-api is mapped to port 9100 in docker-compose.
    base_url = "http://localhost:9101"
    
    token = generate_test_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    print(f"--- Testing Sandbox Worker at {base_url} ---")
    
    # 1. Test Health
    try:
        resp = requests.get(f"{base_url}/health")
        print(f"Health Check: {resp.status_code}")
        print(f"Response: {resp.json()}\n")
    except Exception as e:
        print(f"Health Check Failed: {e}")
        return

    # 2. Test Tool Call (list-dir)
    print("--- Testing Tool: list-dir ---")
    tool_request = {
        "path": "/sandbox",
        "args": {}
    }
    try:
        resp = requests.post(f"{base_url}/tools/list-dir", json=tool_request, headers=headers)
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            print("Successfully listed directory contents.")
            # print(resp.json())
        else:
            print(f"Error: {resp.text}")
    except Exception as e:
        print(f"Tool Call Failed: {e}")

    # 3. Test Tool Call (read-file)
    print("\n--- Testing Tool: read-file (requirements.txt) ---")
    tool_request = {
        "path": "/sandbox/requirements.txt",
        "args": {}
    }
    try:
        resp = requests.post(f"{base_url}/tools/read-file", json=tool_request, headers=headers)
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            content = resp.json().get("result", {}).get("content", "")
            print(f"File content (first 50 chars): {content[:50]}...")
        else:
            print(f"Error: {resp.text}")
    except Exception as e:
        print(f"Tool Call Failed: {e}")

if __name__ == "__main__":
    test_sandbox_tools()
