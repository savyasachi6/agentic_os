# Component: Voice Pipeline (`voice`)

The Voice component provides the Agent OS with the ability to "hear" and "speak," enabling hands-free interaction with the agent system.

## Responsibility & Boundaries

- **Speech-to-Text (STT)**: Transcribes user audio into text streams through `stt_engine.py`.
- **Text-to-Speech (TTS)**: Converts agent reasoning and answers into natural-sounding audio via `tts_generator.py`.
- **Keyword Spotting**: Listens for "wake words" in the background to activate the core agent loop.

## Inbound & Outbound Dependencies

- **Inbound**: Direct audio stream from the client device.
- **Outbound**:
  - Forwards transcribed text to `agent_core.loop.run_turn_async`.
  - Outputs audio buffers to local speakers or remote WebSocket clients.

## Key Public APIs

### `stt_engine.STTEngine`

- `listen_continuous()`: Starts the background transcription loop.
- `transcribe_buffer(audio_data) -> str`: Processes a single audio chunk.

### `tts_generator.TTSGenerator`

- `speak(text: str)`: Generates and plays audio for the provided message.

## Design Principles

- **Edge-First Inference**: Prefers local, high-performance models (like Whisper for STT and Piper for TTS) to minimize latency and ensure privacy.
- **Low-Latency Streaming**: Implements real-time token-to-speech generation so that the agent begins speaking as the LLM is still reasoning.
- **Interruptible Output**: The voice output can be instantly silenced if the `STTEngine` detects a user interrupt token, mimicking natural human conversation.
