from agents.intent.classifier import classify_intent, Intent

test_queries = [
    "What are the .gitignore best practices for this repository?",
    "Show me the available skills",
    "Where is the code for the GitHub URL?",
    "Write a blog post about RAG",
    "Help me debug this dockerfile",
    "What links do you have for this project?"
]

for q in test_queries:
    intent = classify_intent(q)
    print(f"Query: '{q}' -> Intent: {intent}")
