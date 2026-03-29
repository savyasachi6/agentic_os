"""
intent/classifier.py
====================
Intent classification logic using keyword matching and heuristics.
Priority order (highest to lowest):
  GREETING → MATH → CONTENT → CODE_GEN → CAPABILITY → WEB_SEARCH
  → FILESYSTEM → EXECUTION → RAG_LOOKUP → LLM_DIRECT → COMPLEX_TASK
"""
import re
import logging
from core.agent_types import Intent

logger = logging.getLogger("agentos.intent.classifier")

# ----- Math: checked early because math queries often contain code/web keywords too -----
MATH_PATTERNS = [
    r"\b\d+[a-z]\b",
    r"[\+\-\*\/\^=]{2,}",
    r"\bsqrt\b", r"\bsin\b", r"\bcos\b", r"\btan\b", r"\blog\b",
    r"\bpi\b", r"\b\d+\s*[\+\-\*\/\^]\s*\d+\b",
    r"\bcalculate\b", r"\bconvert\b", r"\bconversion\b",
    r"\bscientific\b", r"\bmath\b", r"\bequation\b", r"\bformula\b",
    r"\bintegral\b", r"\bderivative\b", r"\bmatrix\b",
]

# ----- Greetings: exact short tokens only — do NOT put "help" here -----
GREETING_EXACT = {
    "hi", "hello", "hey", "greetings", "yo", "sup",
    "hi there", "hello there", "whats up", "what's up",
    "good morning", "good evening", "how are you",
}

# Conversational follow-ups that should get a friendly redirect, not be silently dropped
FOLLOWUP_PHRASES = [
    "more details", "tell me more", "what is this",
    "wtf", "really", "lol", "ok", "okay",
]

# ----- Content creation: checked BEFORE web so "today's blog" → CONTENT not WEB -----
CONTENT_KEYWORDS = [
    "write a blog", "write an article", "write a story", "write a post",
    "create content", "content creation", "draft a", "blog post",
    "social media post", "write me a", "generate a report",
    "write content", "article about",
]

# ----- Code / repo: checked before CAPABILITY so "github best practices" → CODE not CAP -----
CODE_KEYWORDS = [
    "write code", "create script", "generate code", "implement ",
    "python script", " script", "how can i create",
    ".gitignore", "dockerfile", "requirements.txt",
    "best practices for", "best practice for",
    "this repository", "this repo", "our codebase", "the codebase",
    "refactor", "debug this", "fix this bug", "optimize this",
    "code review", "linting", "unit test", "write tests",
]
# ----- Explanations: checked BEFORE code so "explain code" → LLM_DIRECT not specialist -----
EXPLAIN_KEYWORDS = [
    "explain", "how does", "what is", "describe", "summarize",
    "tell me about", "guide", "tutorial", "patterns in",
    "architecture of", "how to use", "overview",
]

# Note: bare "python" removed — too broad; math queries like "sin(x) in python" must hit MATH first

# ----- Capability: human-facing queries about what the system CAN do -----
CAPABILITY_KEYWORDS = [
    "what can you do", "capabilities", "how can you help",
    "what skills", "list tools", "show skills", "available tools",
    "abilities", "what is indexed", "tell me about your tools",
    "list your tools", "project links", "documentation",
    "who are you", "how do you work", "what is your flow",
    "what are you",
]
CAPABILITY_SINGLE_WORDS = {"menu", "commands"}
# Removed "list" — too generic; "list all agents" should be CAPABILITY but
# we catch that via CAPABILITY_KEYWORDS substring "list tools" / "available tools"

WEB_ONLY_KEYWORDS = [
    "news", "breaking", "current events", "live score",
    "stock price", "weather", "sports score", "recently",
    "trending", "headlines", "search the web", "google",
    "what's the news", "what happened today", "current headlines",
    "latest news",
]
# "today" and "latest" removed — too broad; they appear in many non-web queries

EXECUTION_KEYWORDS = ["run ", "execute ", "train ", "launch ", "start ", "deploy "]

FILESYSTEM_PATTERNS = [
    r"[a-zA-Z]:\\", r"/mnt/[a-z]/", r"/home/\w+/",
    r"access.{0,20}folder", r"access.{0,20}file",
    r"list.{0,20}contents", r"show.{0,20}files",
]

INDEXED_TOPICS = [
    "langchain", "langgraph", "crewai", "autogen", "antigravity",
    "rag", "retrieval", "embedding", "chunking", "pgvector",
    "hybrid search", "semantic cache", "speculative",
    "security principle", "security standard", "security policy",
    "skills", "available skills", "explain skills", "features",
    "how do you think", "mcp", "mcp server", "model context protocol",
    "server", "package", "packages", "dependencies", "requirements",
    "setup", "docker", "docker compose", "container",
]
# Removed bare "capabilities" and "best practice" — both conflict with
# CAPABILITY_KEYWORDS and CODE_KEYWORDS respectively.

LLM_DIRECT_TASKS = [
    "outline", "plan", "explain", "describe", "summarize",
    "architecture", "patterns", "design", "guide", "tutorial",
    "what is", "what are", "how does", "how do", "tell me about",
    "what packages", "what dependencies", "what libraries",
    "what modules", "how to install", "how to configure",
    "difference between", "compare", "pros and cons",
]
OS_TASKS = ["run", "execute", "pip", "install", "launch", "delete", "remove"]


def classify_intent(message: str) -> Intent:
    """
    Classify the incoming message into an Intent enum.
    Priority order is explicit and documented above.
    """
    if not isinstance(message, str):
        message = str(message)
    msg = message.strip().lower()
    logger.debug("Classifying: %r", msg[:120])

    # 1. GREETING — exact-match short tokens only
    if msg in GREETING_EXACT:
        return Intent.GREETING
    if any(msg == phrase for phrase in FOLLOWUP_PHRASES):
        return Intent.GREETING

    # 2. MATH — before CODE so "calculate in python" → MATH not CODE
    if any(re.search(p, msg) for p in MATH_PATTERNS):
        return Intent.MATH

    # 3. CONTENT — before WEB so "write a blog post about today" → CONTENT not WEB
    if any(kw in msg for kw in CONTENT_KEYWORDS):
        return Intent.CONTENT

    # 4. EXPLANATION — before CODE so "explain code" → LLM_DIRECT not code worker
    if any(kw in msg for kw in EXPLAIN_KEYWORDS):
        return Intent.LLM_DIRECT

    # 5. CODE_GEN — before CAPABILITY so "github best practice" → CODE not CAP
    if any(kw in msg for kw in CODE_KEYWORDS):
        return Intent.CODE_GEN

    # 5. CAPABILITY
    if (
        any(re.search(rf"\b{re.escape(kw)}\b", msg) for kw in CAPABILITY_KEYWORDS)
        or msg in CAPABILITY_SINGLE_WORDS
    ):
        return Intent.CAPABILITY_QUERY

    # 6. WEB_SEARCH
    if any(kw in msg for kw in WEB_ONLY_KEYWORDS):
        return Intent.WEB_SEARCH

    # 7. FILESYSTEM
    if any(re.search(p, msg) for p in FILESYSTEM_PATTERNS):
        return Intent.FILESYSTEM

    # 8. EXECUTION
    if any(msg.startswith(kw) for kw in EXECUTION_KEYWORDS):
        return Intent.EXECUTION

    # 9. RAG_LOOKUP
    if any(topic in msg for topic in INDEXED_TOPICS):
        return Intent.RAG_LOOKUP

    # 10. LLM_DIRECT — pure generative tasks with no tool requirement
    if is_llm_generatable(msg):
        return Intent.LLM_DIRECT

    # 11. COMPLEX_TASK — default for anything long and ambiguous
    # Phase 15 Hardening: ensure SIMPLE_TASK (word_count <= 2) is removed
    # or handled explicitly. We return COMPLEX_TASK here for safety.
    return Intent.COMPLEX_TASK


def is_llm_generatable(task: str) -> bool:
    """Return True only when the task is purely generative (no OS/tool requirement)."""
    if any(kw in task for kw in OS_TASKS):
        return False
    return any(kw in task for kw in LLM_DIRECT_TASKS)
