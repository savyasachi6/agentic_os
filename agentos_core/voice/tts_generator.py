import asyncio
from typing import Optional

class TTSGenerator:
    """
    Text-to-Speech Generator (TTS)
    As specified in agentos_core/docs/components/voice.md
    """
    def __init__(self, voice_id: Optional[str] = None):
        self.voice_id = voice_id
        print(f"[TTSGenerator] Initialized with voice: {self.voice_id or 'Piper-Base'}")

    async def speak(self, text: str):
        """
        Generates and plays audio for the provided message.
        Follows 'Low-Latency Streaming' principle.
        """
        print(f"[TTSGenerator] Speaking: {text}")
        # In a real implementation, this would stream to an audio output device
        await asyncio.sleep(0.1)
