import asyncio
from typing import List, Dict, Optional, AsyncGenerator
from .base import LLMBackend

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

    async def generate_stream(
        self,
        messages: List[Dict[str, str]],
        model: str,
        max_tokens: int,
        temperature: float,
        stop: Optional[List[str]] = None,
    ) -> AsyncGenerator[Dict[str, str], None]:
        """
        Stream tokens from the native Llama model.
        Runs the stream iteration in a separate thread.
        """
        loop = asyncio.get_running_loop()
        
        if self.llm is None:
            async with self._load_lock:
                if self.llm is None:
                    await loop.run_in_executor(None, self._load_model_sync)

        # Offload the blocking stream generation to a thread
        def stream_generator():
            try:
                # llama-cpp-python supports OpenAI-style streaming
                for chunk in self.llm.create_chat_completion(
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stop=stop,
                    stream=True
                ):
                    delta = chunk["choices"][0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield {"type": "token", "content": content}
            except Exception as e:
                print(f"[LlamaCPPBackend] Streaming error: {e}")
                yield {"type": "error", "content": str(e)}

        # Wrap the synchronous generator into an async one
        # Note: In a production system, use an asyncio.Queue to decouple
        gen = stream_generator()
        while True:
            try:
                # We fetch from the generator in the current thread since it's already yielded
                # but let's be safe and use run_in_executor if the generator was heavy (not here)
                val = await loop.run_in_executor(None, next, gen)
                yield val
            except StopIteration:
                break
            except Exception as e:
                yield {"type": "error", "content": str(e)}
                break

    async def generate_batch(self, messages_batch: List[List[Dict[str, str]]], model: str, max_tokens: int, temperature: float, stop: Optional[List[str]] = None) -> List[str]:
        """
        Fire concurrent async requests.
        Consumes generate_stream for each item.
        """
        async def fetch(messages: List[Dict[str, str]]) -> str:
            full_content = []
            async for chunk in self.generate_stream(messages, model, max_tokens, temperature, stop):
                if chunk["type"] == "token":
                    full_content.append(chunk["content"])
                elif chunk["type"] == "error":
                    raise ValueError(chunk["content"])
            return "".join(full_content)

        tasks = [fetch(msgs) for msgs in messages_batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        processed = []
        for r in results:
            if isinstance(r, Exception):
                processed.append(f"[Error: {r}]")
            else:
                processed.append(str(r))
        return processed
