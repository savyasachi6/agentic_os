"""
LLM client: adapter for local model inference via Ollama.
Now routes all generation through the centralized LLMRouter.
"""

import time
import asyncio
from typing import List, Dict, Generator, Optional

from agent_config import model_settings
from llm_router import LLMRouter

class LLMClient:
    def __init__(
        self,
        model_name: str = None,
        temperature: float = None,
        max_tokens: int = None,
    ):
        self.model_name = model_name or model_settings.llm_model
        self.temperature = temperature or model_settings.llm_temperature
        self.max_tokens = max_tokens or model_settings.llm_max_tokens
        self.router = LLMRouter.get_instance()

    async def generate_async(
        self,
        messages: List[Dict[str, str]],
        session_id: str = "default_session",
    ) -> str:
        """
        Asynchronous generation. Submits the request to the central LLMRouter
        and awaits the batched response.
        """
        try:
            return await self.router.submit(
                messages=messages,
                session_id=session_id,
                model=self.model_name,
                max_tokens=self.max_tokens,
                temperature=self.temperature
            )
        except Exception as e:
            err_msg = f"[Agent error: {e}]"
            print(f"[llm] Router error: {e}")
            return err_msg

    def generate(
        self,
        messages: List[Dict[str, str]],
        retries: int = 3,
    ) -> str:
        """
        Synchronous wrapper around generate_async. 
        Maintains backward compatibility for sync call sites.
        """
        try:
            # Check if we are already in an event loop
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
            
        if loop and loop.is_running():
            # Not natively supported to blockingly run an async function from within an async loop in Python
            # without nested loops or threads. As the architecture shifts to async-first, async callers
            # should use generate_async directly.
            print("[llm] Warning: Called sync generate() from within an async loop. This may fail.")
            raise RuntimeError("Cannot call synchronous generate() from an active asyncio event loop. Use generate_async().")
        else:
            return asyncio.run(self.generate_async(messages))

    def generate_streaming(
        self,
        messages: List[Dict[str, str]],
    ) -> Generator[str, None, None]:
        """
        Streaming generation. 
        Note: The LLMRouter currently batches complete generations.
        For true streaming, the router would need an async generator demuxer.
        For now, this falls back to direct Ollama streaming if required by WS.
        """
        import ollama
        try:
            stream = ollama.chat(
                model=self.model_name,
                messages=messages,
                stream=True,
                options={
                    "temperature": self.temperature,
                    "num_predict": self.max_tokens,
                },
            )
            for chunk in stream:
                token = chunk.get("message", {}).get("content", "")
                if token:
                    yield token
        except Exception as e:
            yield f"\n[LLM Stream Error] {e}"

    def summarize(self, text: str, max_summary_tokens: int = 200) -> str:
        """
        Ask the model to produce a concise summary of the given text.
        """
        messages = [
            {
                "role": "system",
                "content": "You are a summarization assistant. Produce a concise summary of the following text in 2-3 sentences.",
            },
            {"role": "user", "content": text},
        ]
        return self.generate(messages)

from pydantic import BaseModel
import json

async def generate_structured_output(prompt: str, response_model: BaseModel, system_prompt: str = "") -> BaseModel:
    """
    Generates structured JSON output explicitly conforming to the provided Pydantic model.
    """
    llm = LLMClient(model_name=model_settings.fast_model, temperature=0.0)
    messages = []
    
    if system_prompt:
        schema_json = json.dumps(response_model.model_json_schema(), indent=2)
        system_content = f"{system_prompt}\n\nYou must respond ONLY with pure JSON that validates against this JSON schema. Do not wrap it in markdown block quotes.\n\n{schema_json}"
        messages.append({"role": "system", "content": system_content})
        
    messages.append({"role": "user", "content": prompt})

    try:
        # Structured output relies on format="json", which isn't exposed in our router yet.
        # Fallback to direct Ollama for this specific utility until router supports kwargs mapping.
        import ollama
        response = ollama.chat(
            model=llm.model_name,
            messages=messages,
            format="json",
            options={"temperature": 0.0}
        )
        raw_json = response["message"]["content"]
        
        if raw_json.startswith("```json"):
            raw_json = raw_json[7:]
        if raw_json.endswith("```"):
             raw_json = raw_json[:-3]
             
        parsed_data = json.loads(raw_json)
        return response_model(**parsed_data)
        
    except Exception as e:
        print(f"[llm] Failed parsing structured output: {e}")
        return response_model()

def get_llm() -> LLMClient:
    """Helper to return the default LLMClient."""
    return LLMClient()
