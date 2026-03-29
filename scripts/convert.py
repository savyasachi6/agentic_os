import os

prompts_dir = 'assets/prompts'
os.makedirs('prompts', exist_ok=True)

for root, _, files in os.walk(prompts_dir):
    for filename in files:
        if filename.endswith('.md'):
            src = os.path.join(root, filename)
            agent_name = filename[:-3]
            var_name = agent_name.upper().replace('-', '_') + '_SYSTEM_PROMPT'
            dst = os.path.join('prompts', agent_name.replace('-', '_') + '.py')
            
            with open(src, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            
            content = content.replace('"""', '\\"\\"\\"')
            
            with open(dst, 'w', encoding='utf-8') as f:
                f.write(f'{var_name} = """{content}"""\n')
            
            print(f'Converted {src} to {dst}')

print('Prompts extraction complete.')
