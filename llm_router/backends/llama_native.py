import asyncio
from typing import List, Dict, Optional
from llm_router.backends.base import LLMBackend

class LlamaCPPBackend(LLMBackend):
    def __init__(self, model_path: str):
        self.model_path = model_path
        self.llm = None
        self._load_lock = asyncio.Lock()
        
    def _load_model_sync(self):
        """Loads the Llama model synchronously inside a worker thread."""
        try:
            from llama_cpp import Llama
            print(f"[LlamaCPPBackend] Loading model directly into Python memory from {self.model_path}...")
            # Loads the model with GPU offloading
            self.llm = Llama(
                model_path=self.model_path,
                n_gpu_layers=-1, 
                n_ctx=4096, 
                verbose=True
            )
            print(f"[LlamaCPPBackend] Model successfully loaded.")
        except ImportError:
            raise ImportError(
                "llama-cpp-python is not installed. Please install it with proper CUDA flags."
            )
        except Exception as e:
            raise RuntimeError(f"Failed to load Llama model from {self.model_path}. Error: {e}")

    async def generate_batch(self, messages_batch: List[List[Dict[str, str]]], model: str, max_tokens: int, temperature: float, stop: Optional[List[str]] = None) -> List[str]:
        """
        Runs inference natively without network overhead.
        We run this in a thread executor to prevent blocking the async event loop.
        """
        loop = asyncio.get_running_loop()
        
        if self.llm is None:
            async with self._load_lock:
                if self.llm is None:
                    # Offload the heavy synchronous model load from the async event loop
                    await loop.run_in_executor(None, self._load_model_sync)
        
        def run_inference(messages):
            try:
                # llama-cpp-python supports the chat completions format directly!
                res = self.llm.create_chat_completion(
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stop=stop
                )
                return res["choices"][0]["message"]["content"]
            except Exception as e:
                print(f"[LlamaCPPBackend] Error running inference: {e}")
                return f"[Error: {e}]"

        # Even though these run in threads, Llama respects its internal queue and GIL context
        tasks = [
            loop.run_in_executor(None, run_inference, msgs)
            for msgs in messages_batch
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        processed = []
        for r in results:
            if isinstance(r, Exception):
                processed.append(f"[Error: {r}]")
            else:
                processed.append(str(r))
                
        return processed
