from agents.intent.classifier import classify_intent
from core.agent_types import Intent

test_cases = [
    ("hi", Intent.GREETING),
    ("calculate sin(45)", Intent.MATH),
    ("convert 5 km to miles", Intent.MATH),
    ("convert 5 km to miles in python", Intent.MATH),
    ("write a blog post about today's AI trends", Intent.CONTENT),
    ("what can you do", Intent.CAPABILITY_QUERY),
    ("best practices for .gitignore", Intent.CODE_GEN),
    ("what is RAG", Intent.RAG_LOOKUP),
    ("latest news about OpenAI", Intent.WEB_SEARCH),
    ("explain transformer architecture", Intent.LLM_DIRECT),
    ("run docker-compose up", Intent.EXECUTION),
    ("foo bar", Intent.COMPLEX_TASK),
]

print("--- Phase 15: Intent Classification Audit ---")
all_passed = True
for query, expected in test_cases:
    actual = classify_intent(query)
    status = "PASS" if actual == expected else "FAIL"
    print(f"[{status}] Query: '{query}'")
    print(f"       Expected: {expected}")
    print(f"       Actual:   {actual}")
    if actual != expected:
        all_passed = False

if all_passed:
    print("\n✅ ALL 12 AUDIT CASES PASSED!")
else:
    print("\n❌ SOME AUDIT CASES FAILED.")
