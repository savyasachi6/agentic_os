import os
import re

def refactor_loader(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        new_content = content.replace('from prompts.loader import load_prompt', 'from prompts.loader import load_prompt')
        new_content = new_content.replace('from prompts import loader', 'from prompts import loader')
        new_content = new_content.replace('loader.load_prompt', 'loader.load_prompt')
        
        # Replace occurrences of load_prompt("coordinator") with load_prompt("coordinator")
        new_content = re.sub(r'load_prompt\([\'"][a-zA-Z0-9_-]+[\'"],\s*([\'"][a-zA-Z0-9_-]+[\'"])\)', r'load_prompt(\1)', new_content)

        if content != new_content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f'Refactored loader in: {filepath}')
    except Exception as e:
        pass

for root, dirs, files in os.walk('.'):
    # Skip .git, .venv, etc.
    if any(i in root for i in ['.git', '.venv', 'node_modules', 'dist', 'build', 'prompts']):
        continue
    for f in files:
        if f.endswith('.py'):
            refactor_loader(os.path.join(root, f))

print('Prompt refactor complete.')
