# scripts/verify_tools.py
# Run this FIRST to confirm what's actually registered

import asyncio
import asyncpg
from agent_core.config import settings

async def verify():
    try:
        pool = await asyncpg.create_pool(settings.database_url)
    except Exception as e:
        print(f"Failed to connect to DB: {e}")
        return
    
    # Check tools table
    try:
        tools = await pool.fetch("SELECT name, risk_level, endpoint FROM tools ORDER BY name")
        print(f"\n{'='*50}")
        print(f"Tools in DB: {len(tools)}")
        for t in tools:
            print(f"  {t['name']:30} {t['risk_level']:8} {t['endpoint']}")
        
        # Check if web_search tool exists
        web_tool = await pool.fetchrow(
            "SELECT * FROM tools WHERE name = 'web_search'"
        )
        print(f"\nweb_search registered: {'YES' if web_tool else 'NO'}")
    except Exception as e:
        print(f"Error querying tools table: {e}")
    
    # Check Browser
    try:
        r = requests.get("http://localhost:9222/json/version", timeout=2)
        if r.status_code == 200:
            print(f"Browser alive: YES {r.json()}")
        else:
            print(f"Browser alive: NO status={r.status_code}")
    except Exception as e:
        print(f"Browser alive: NO {e}")
    
    await pool.close()

if __name__ == "__main__":
    asyncio.run(verify())
