import urllib.request
import json
import time

def pull_model(model_name):
    print(f"Pulling {model_name}...")
    req = urllib.request.Request("http://localhost:11434/api/pull", 
                                 data=json.dumps({"name": model_name}).encode("utf-8"), 
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as response:
        for line in response:
            pass # read completely
    print("Pulled")

def get_embed_dim(model_name):
    req = urllib.request.Request("http://localhost:11434/api/embeddings", 
                                 data=json.dumps({"model": model_name, "prompt": "test"}).encode("utf-8"), 
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read())
        return len(data["embedding"])

if __name__ == "__main__":
    pull_model("qwen:0.5b") # Qwen 1.5/2.5 often tagged without version for base, or "qwen2.5:0.5b"
    print(get_embed_dim("qwen:0.5b"))
