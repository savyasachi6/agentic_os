# LLM Router API Reference

## `LLMRouter` (Singleton)

The primary interface for submitting inference requests.

### Methods

#### `get_instance() -> LLMRouter`

Returns the global singleton instance.

#### `start()`

Initializes the background batching loop. Must be called before any `submit()` calls.

#### `stop()`

Cancels the background loop and clears the queue.

#### `submit(messages, session_id, model, max_tokens=2048, temperature=0.7) -> str` (Async)

Submits a request to the batching queue.

- **messages**: List of OpenAI-style message dicts.
- **Returns**: The generated content string.
- **Raises**: `RuntimeError` if the backend fails.

## `LLMBackend` (Interface)

Extend this class to add support for new inference engines.

### Methods

#### `generate_batch(messages_batch, model, max_tokens, temperature) -> List[str]` (Async)

Executes a batch of requests.

- **messages_batch**: A list of message lists.
- **Returns**: A list of completion strings, mapping 1:1 to the input lists.
