# Voice Pipeline API Reference

## `voice.adapter`

### `ASRAdapter` (Base Class)

- `transcribe_stream(audio_generator) -> AsyncGenerator[str]`: Takes an async generator of audio chunks and yields transcribed text segments.
- `transcribe_file(file_path) -> str`: transcribes a static audio file.

### `TTSAdapter` (Base Class)

- `synthesize_to_stream(text) -> AsyncGenerator[bytes]`: Takes text and yields audio byte chunks for immediate playback.
- `synthesize_to_file(text, output_path) -> bool`: Saves synthesized speech to a file.

## `voice.stream`

- `AudioStreamer`: Handles microphone input and speaker output.
  - `start_mic_stream()`: Begins capturing audio from the default input device.
  - `play_buffer(audio_bytes)`: queues audio for playback.
  - `stop()`: Closes all audio streams.

- `VoiceActivityDetector`: Analyzes audio buffers to detect speech boundaries.
  - `is_speaking(buffer) -> bool`: Returns True if the buffer contains active speech.
