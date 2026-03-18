# Voice Domain

The **Voice Domain** in `core` manages the audio interface for the Agent OS appliance, providing natural language STT (Speech-to-Text) and TTS (Text-to-Speech) capabilities.

## Responsibility

It enables "eyes-free" interaction by processing raw audio streams into text that the `agent_core` can understand and synthesizing the agent's reasoning back into human-like speech.

## Key Sub-modules

- **Audio Streamer**:
  - Low-latency interface for capturing mic input and routing speaker output.
- **Inference Adapter (STT/TTS)**:
  - Lightweight wrappers for local model inference (e.g., Whisper for STT, Piper or Coqui for TTS).
- **Phonic Pre-processor**:
  - Filters background noise and identifies user "wake words" before triggering the agent's main loop.

## Dependencies

- **Inbound**:
  - External hardware (Microphone/Speakers).
- **Outbound**:
  - `agent_core.loop`: Provides transcribed text for reasoning.
  - `core.llm`: Receives text to synthesize into speech.

## Design Patterns

- **Stream Buffer**: Audio data is buffered in circular buffers to ensure playback doesn't stutter even during heavy CPU-bound LLM inference.
