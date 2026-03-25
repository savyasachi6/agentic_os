# scripts/register_tools.py — ADD web_search

import asyncio
import asyncpg
from agent_core.config import settings
import os

MISSING_TOOLS = [
    {
        "name": "web_search",
        "description": (
            "Search the live web using Lightpanda headless browser "
            "at localhost:9222. Use for news, current events, live data, "
            "any query needing real-time information."
        ),
        "risk_level": "low",
        "endpoint": "http://localhost:9222",
        "tags": ["web", "search", "news", "live", "browser", "lightpanda"]
    },
    {
        "name": "web_scrape",
        "description": (
            "Scrape content from a specific URL using Lightpanda browser. "
            "Handles JavaScript-rendered pages. Returns full page text."
        ),
        "risk_level": "low",
        "endpoint": "http://localhost:9222",
        "tags": ["web", "scrape", "browser", "lightpanda", "url"]
    },
    {
        "name": "web_navigate",
        "description": (
            "Navigate to any URL and extract content using "
            "Lightpanda headless browser. Full JS rendering."
        ),
        "risk_level": "low",
        "endpoint": "http://localhost:9222",
        "tags": ["web", "navigate", "browser", "lightpanda"]
    },
]

async def register():
    host = os.getenv("POSTGRES_HOST", "localhost")
    # Or just use the settings as is if we passed the env var
    try:
        pool = await asyncpg.create_pool(settings.database_url)
    except Exception as e:
        print(f"Failed to connect to DB: {e}")
        return

    for tool in MISSING_TOOLS:
        await pool.execute("""
            INSERT INTO tools (name, description, risk_level, endpoint, tags)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (name) DO UPDATE SET
                description = EXCLUDED.description,
                endpoint    = EXCLUDED.endpoint,
                tags        = EXCLUDED.tags
        """, tool["name"], tool["description"],
            tool["risk_level"], tool["endpoint"], tool["tags"])
        print(f"Registered: {tool['name']}")
    
    count = await pool.fetchval("SELECT COUNT(*) FROM tools")
    print(f"\nTotal tools: {count}")
    await pool.close()

if __name__ == "__main__":
    asyncio.run(register())
