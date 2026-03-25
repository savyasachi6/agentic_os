import os
import subprocess
import sys

def install_llama_cpp():
    print("=== 1/3 Installing pre-compiled llama-cpp-python (CUDA 12.2) ===")
    
    # We use pre-compiled Windows wheels to bypass the need for Visual Studio Build Tools
    # Your standard Nvidia game-ready drivers usually include the CUDA 12.x runtime libraries natively.
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "llama-cpp-python",
             "--extra-index-url", "https://abetlen.github.io/llama-cpp-python/whl/cu124",
             "--upgrade", "--no-cache-dir"]
        )
        print("Successfully installed llama-cpp-python with CUDA!")
    except subprocess.CalledProcessError as e:
        print(f"\n[ERROR] Failed to install pre-compiled llama-cpp-python: {e}")
        print("If this fails, you may need to install the CPU-only version by running:")
        print("  pip install llama-cpp-python")
        sys.exit(1)

def download_model():
    print("\n=== 2/3 Downloading Qwen GGUF Model ===")
    
    # Install huggingface-hub if not present
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        print("Installing huggingface-hub...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "huggingface-hub"])
        from huggingface_hub import hf_hub_download

    # Save models one directory up, in `agentic_os/models/`
    core_dir = os.path.dirname(os.path.abspath(__file__))
    models_dir = os.path.abspath(os.path.join(core_dir, "..", "models"))
    os.makedirs(models_dir, exist_ok=True)
    
    repo_id = "Qwen/Qwen2.5-Coder-7B-Instruct-GGUF"
    filename = "qwen2.5-coder-7b-instruct-q4_k_m.gguf"
    
    print(f"Downloading {filename} from {repo_id}...")
    print("This may take several minutes depending on your internet connection (approx 4.5 GB)...")
    
    # hf_hub_download handles resuming interrupted downloads automatically!
    model_path = hf_hub_download(
        repo_id=repo_id, 
        filename=filename, 
        local_dir=models_dir
    )
    print(f"Model downloaded successfully to: {model_path}")
    return model_path

def update_env(model_path):
    print("\n=== 3/3 Updating .env configuration ===")
    
    core_dir = os.path.dirname(os.path.abspath(__file__))
    env_file = os.path.abspath(os.path.join(core_dir, "..", ".env"))
    
    print(f"Targeting environment file: {env_file}")
    
    # Convert backslashes for python compatibility if needed, or leave raw paths
    safe_model_path = str(model_path).replace("\\", "\\\\")
    
    env_vars = {
        "ROUTER_BACKEND": "llama-cpp",
        "LLAMA_CPP_MODEL_PATH": safe_model_path
    }
    
    lines = []
    if os.path.exists(env_file):
        with open(env_file, "r") as f:
            lines = f.readlines()
            
    new_lines = []
    found_keys = set()
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue
            
        key = stripped.split("=")[0]
        if key in env_vars:
            new_lines.append(f"{key}={env_vars[key]}\n")
            found_keys.add(key)
        else:
            new_lines.append(line)
            
    # Remove trailing newlines cleanly
    while new_lines and new_lines[-1] == "\n":
        new_lines.pop()
        
    new_lines.append("\n")
    
    for key, val in env_vars.items():
        if key not in found_keys:
            new_lines.append(f"{key}={val}\n")
            
    with open(env_file, "w") as f:
        f.writelines(new_lines)
        
    print(f"Updated {env_file} to automatically boot the Native Llama-CPP pipeline.")

if __name__ == "__main__":
    install_llama_cpp()
    model_path = download_model()
    update_env(model_path)
    print("\n=== Setup Complete! ===")
    print("You can now run `python main.py serve` to boot Agentic OS natively on your VRAM.")
