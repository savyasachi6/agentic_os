# config.py
import os
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from agent_config.settings import db_settings, model_settings, redis_settings

@dataclass
class Config:
    # Database (Bridging from agent_config.settings)
    POSTGRES_DSN: str = field(default_factory=lambda: db_settings.dsn)
    REDIS_URL: str = field(default_factory=lambda: redis_settings.url)
    
    # LLM (Bridging from agent_config.settings)
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "ollama")  # ollama | openai | anthropic
    LLM_MODEL: str = field(default_factory=lambda: model_settings.llm_model)
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "http://localhost:11434")
    EMBED_MODEL: str = field(default_factory=lambda: model_settings.embed_model)
    EMBED_DIM: int = field(default_factory=lambda: model_settings.embed_dim)
    
    # MCP
    MCP_SERVERS: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    # Guards
    MAX_AGENT_CALLS_PER_AGENT: int = 2
    MAX_TOTAL_AGENT_CALLS: int = 8
    MAX_ITERATIONS: int = 10
    
    # Cache
    CACHE_SIMILARITY_THRESHOLD: float = 0.88
    CACHE_TTL_SECONDS: int = 3600
    
    # Risk
    HIGH_RISK_KEYWORDS: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        if not self.MCP_SERVERS:
            self.MCP_SERVERS = {
                "filesystem": {
                    "transport": "stdio",
                    "command": "npx @modelcontextprotocol/server-filesystem C:\\Users\\savya"
                },
                "memory": {
                    "transport": "stdio",
                    "command": "npx @modelcontextprotocol/server-memory"
                },
                "postgres": {
                    "transport": "stdio",
                    "command": "npx @modelcontextprotocol/server-postgres"
                },
                "github": {
                    "transport": "stdio",
                    "command": "npx @modelcontextprotocol/server-github"
                },
                "fetch": {
                    "transport": "stdio",
                    "command": "npx @modelcontextprotocol/server-fetch"
                },
                "brave": {
                    "transport": "stdio",
                    "command": "npx @modelcontextprotocol/server-brave-search",
                    "env": {"BRAVE_API_KEY": os.getenv("BRAVE_API_KEY", "")},
                    "description": "Web search via Brave — for news, current events, web facts",
                    "fallback_for": ["news", "today", "latest", "current", "weather"]
                },
                "puppeteer": {
                    "transport": "stdio",
                    "command": "npx @modelcontextprotocol/server-puppeteer"
                },
            }
        if not self.HIGH_RISK_KEYWORDS:
            self.HIGH_RISK_KEYWORDS = [
                "rm ", "sudo", "pip install", "train", "launch",
                "delete", "format", "chmod", "kill", "reboot",
                "drop table", "deploy", "npm install", "apt"
            ]

config = Config()
