import pytest
from voice.stt_engine import STTEngine
from voice.tts_generator import TTSGenerator

def test_voice_interface_alignment():
    """Verify that the classes and methods match the docs."""
    stt = STTEngine()
    tts = TTSGenerator()
    
    assert hasattr(stt, "listen_continuous"), "STTEngine missing documented method 'listen_continuous'"
    assert hasattr(stt, "transcribe_buffer"), "STTEngine missing documented method 'transcribe_buffer'"
    assert hasattr(tts, "speak"), "TTSGenerator missing documented method 'speak'"

@pytest.mark.asyncio
async def test_stt_transcribe_stub():
    stt = STTEngine()
    result = await stt.transcribe_buffer(b"dummy_audio")
    assert result == "Simulated transcription."

@pytest.mark.asyncio
async def test_tts_speak_stub():
    tts = TTSGenerator()
    # Should not raise errors
    await tts.speak("Hello alignment")
