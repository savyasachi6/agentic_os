import ollama
from core.settings import settings as model_settings

def test_ollama_embeddings():
    print(f"Testing Ollama integration with model: {model_settings.embed_model}")
    
    test_text = "The quick brown fox jumps over the lazy dog."
    
    try:
        response = ollama.embeddings(model=model_settings.embed_model, prompt=test_text)
        embedding = response.get("embedding")
        
        if embedding:
            print(f"Successfully generated embedding!")
            print(f"Dimension: {len(embedding)}")
            print(f"First 5 values: {embedding[:5]}")
            return True
        else:
            print("Failed: No embedding found in response.")
            return False
            
    except Exception as e:
        print(f"Error during Ollama embedding test: {e}")
        return False

if __name__ == "__main__":
    success = test_ollama_embeddings()
    if success:
        print("\nOllama Embedding Integration: [VERIFIED]")
    else:
        print("\nOllama Embedding Integration: [FAILED]")
