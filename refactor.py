import os
import re

root_dir = r"C:\Users\savya\projects\agentic_os"

def replace_in_file(rel_path, replacements):
    path = os.path.join(root_dir, rel_path)
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    
    new_content = content
    for old, new in replacements:
        new_content = new_content.replace(old, new)
        
    if new_content != content:
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"Updated {rel_path}")

# 1. Configs
config_replacements = [
    ("default=768", "default=1024"),
    ("default=\"nomic-embed-text\"", "default=\"qwen:0.5b\""),
    ("default=\"llama3.2\"", "default=\"qwen3-vl:8b\""),
    ("fast_model: str = Field(default=\"llama3.2:3b\", alias=\"FAST_MODEL\")", "fast_model: str = Field(default=\"qwen:0.5b\", alias=\"FAST_MODEL\")")
]
replace_in_file(r"agentic_os\config.py", config_replacements)
replace_in_file(r"agentos_core\config.py", config_replacements)

# 2. Docker Compose & .env
env_replacements = [
    ("LLM_MODEL=llama3.2", "LLM_MODEL=qwen3-vl:8b"),
    ("EMBED_MODEL=nomic-embed-text", "EMBED_MODEL=qwen:0.5b")
]
replace_in_file(r"agentos_core\docker-compose.yml", env_replacements)
replace_in_file(r".env.example", env_replacements)

# 3. Schema
schema_replacements = [
    ("VECTOR(768)", "VECTOR(1024)"),
    ("DEFAULT 768", "DEFAULT 1024")
]
replace_in_file(r"agentos_memory\agent_memory\schema.sql", schema_replacements)

# 4. Tests
test_replacements = [
    ("768", "1024")
]
replace_in_file(r"agentos_memory\tests\test_rag_schema.py", test_replacements)
replace_in_file(r"agentos_memory\tests\test_tree_store_unit.py", test_replacements)

# 5. Docs and Markdown
doc_replacements = [
    ("768", "1024"),
    ("nomic-embed-text", "qwen:0.5b")
]
replace_in_file(r"skill.md", doc_replacements)
replace_in_file(r"agentos_memory\docs\rag_schema_design.md", doc_replacements)
replace_in_file(r"agentos_memory\docs\api.md", doc_replacements)
replace_in_file(r"agentos_memory\docs\adr\001-pgvector-and-embeddings.md", doc_replacements)
replace_in_file(r"docs\architecture\memory_schema.md", doc_replacements)

# AgentOS Context doc
replace_in_file(r"docs\agentic_os_context_for_llm.md.resolved", doc_replacements)

print("Refactor complete.")
