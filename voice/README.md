# Voice Pipeline (`voice/`)

Translates between streaming audio and natural language text.

## Purpose

Enables hands-free, low-latency interaction with the Agent OS. It isolates speech processing (ASR/TTS) from the reasoning loop.

## Features

- **Streaming ASR**: Transcribes microphone input in real-time.
- **Async TTS**: Synthesizes response audio with low-latency buffering.
- **Provider Adapters**: Supports Whisper, Piper, Google Cloud, and OpenAI.

## Usage

```python
from voice.stream import AudioStreamer
from voice.adapter import ASRAdapter

streamer = AudioStreamer()
# Start listening and transcribing...
```

See [docs/architecture.md](docs/architecture.md) for details.
