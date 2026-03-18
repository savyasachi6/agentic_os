"""Quick WebSocket sanity check — sends one message, prints events, exits."""
import asyncio, json, sys
sys.path.insert(0, ".")

async def test():
    try:
        import websockets
    except ImportError:
        print("pip install websockets first")
        return

    uri = "ws://localhost:8000/chat"
    print(f"Connecting to {uri}...")
    try:
        async with websockets.connect(uri, open_timeout=5) as ws:
            await ws.send(json.dumps({"message": "How many documents exist in the system?"}))
            print("Message sent. Waiting for events...")
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=60)
                data = json.loads(raw)
                t, c = data.get("type"), data.get("content", "")
                print(f"  [{t}] {str(c)[:120]}")
                if t in ("final", "error"):
                    break
    except Exception as e:
        print(f"Connection failed: {e}")

asyncio.run(test())
