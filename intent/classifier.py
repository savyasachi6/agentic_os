"""
intent/classifier.py
====================
Intent classification logic using keyword matching and heuristics.
Replaces core/intent_classifier.py.
"""
import re
import logging
from typing import Optional
from agent_core.agent_types import Intent # Now imported from centralized core/types.py

logger = logging.getLogger("agentos.intent.classifier")

# --- Keywords and Patterns ---
CAPABILITY_KEYWORDS = [
    "what can you do", "what are you", "capabilities", "help me",
    "how can you help", "what skills", "list skills", "show skills",
    "available tools", "abilities", "what is indexed", "what are some of the skills",
    "tell me about your skills", "list your skills", "project links", "github", "documentation",
    "repo", "where is the code", "links to this project", "github url", "repo url"
]
CAPABILITY_SINGLE_WORDS = {
    "menu", "commands", "list"
}
GREETING_WORDS = {"hi", "hello", "hey", "greetings", "yo", "sup", "hi there", "hello there"}

WEB_ONLY_KEYWORDS = [
    "news", "today", "latest", "breaking", "current events",
    "live", "stock price", "weather", "sports score", "recently",
    "trending", "headlines", "search the web", "google"
]

EXECUTION_KEYWORDS = ["run ", "execute ", "train ", "launch ", "start ", "deploy "]
CODE_KEYWORDS = ["write code", "create script", "generate code", "implement ", "how can i create", "python script", " script", "python"]

FILESYSTEM_PATTERNS = [
    r"[a-zA-Z]:\\", r"/mnt/[a-z]/", r"/home/\w+/",
    r"access.{0,20}folder", r"access.{0,20}file",
    r"list.{0,20}contents", r"show.{0,20}files"
]

INDEXED_TOPICS = [
    "langchain", "langgraph", "crewai", "autogen", "antigravity",
    "rag", "retrieval", "embedding", "chunking", "pgvector",
    "hybrid search", "semantic cache", "speculative"
]

def classify_intent(message: str) -> Intent:
    """
    Classify the incoming message into an Intent enum.
    Fast, heuristic-based classification.
    """
    if not isinstance(message, str):
        message = str(message)
    msg = message.strip().lower()
    logger.debug("Classifying intent for msg: '%s'", msg)
    
    if any(kw in msg for kw in CAPABILITY_KEYWORDS) or msg in CAPABILITY_SINGLE_WORDS:
        return Intent.CAPABILITY_QUERY

    if msg in GREETING_WORDS:
        return Intent.GREETING

    if any(kw in msg for kw in CODE_KEYWORDS):
        return Intent.CODE_GEN
        
    if any(kw in msg for kw in WEB_ONLY_KEYWORDS):
        return Intent.WEB_SEARCH

    if any(re.search(p, msg) for p in FILESYSTEM_PATTERNS):
        return Intent.FILESYSTEM

    if any(msg.startswith(kw) for kw in EXECUTION_KEYWORDS):
        return Intent.EXECUTION

    if any(topic in msg for topic in INDEXED_TOPICS):
        return Intent.RAG_LOOKUP

    # Default logic (must be after all keyword matches)
    word_count = len(msg.split())
    
    # If it's a known LLM-friendly task like "explain X", use LLM_DIRECT
    if is_llm_generatable(msg):
        return Intent.LLM_DIRECT

    # Very short queries (1-2 words) that aren't keywords are SIMPLE_TASK
    if word_count <= 2:
        return Intent.SIMPLE_TASK
        
    # Everything else long is a COMPLEX_TASK for the orchestrator
    return Intent.COMPLEX_TASK

def is_llm_generatable(task: str) -> bool:
    """Check if task can be handled purely by LLM or requires tool execution."""
    lower = task.lower()
    LLM_TASKS = [
        "outline", "plan", "list", "explain", "describe", "summarize", 
        "architecture", "patterns", "design", "guide", "tutorial"
    ]
    OS_TASKS = ["run", "execute", "pip", "install", "launch", "delete", "remove"]
    
    # Narrower definition: MUST contain an LLM task keyword AND be relatively simple content-wise
    # If it has specific OS keywords, it's NOT purely generatable.
    if any(kw in lower for kw in OS_TASKS):
        return False
        
    return any(kw in lower for kw in LLM_TASKS)
