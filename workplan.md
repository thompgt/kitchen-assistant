# Project Workplan: Real-Time Hands-Free Kitchen Voice Assistant

This document outlines the end-to-end engineering roadmap for building a high-performance, low-latency, real-time voice agent designed for high-noise kitchen environments.

## Architectural Milestones & Timeline

### Phase 1: Core Architecture & Workspace Scaffolding
* **Objective**: Initialize the repository, define schemas, and establish the runtime environment.
* **Tasks**:
    * Set up a Python 3.11+ virtual environment and declare production/development dependencies.
    * Initialize a `FastAPI` application backend structured for asynchronous streaming.
    * Configure a local `Redis` or an in-memory asynchronous key-value store to maintain session state (`RecipeState`).
    * Design pydantic data models for recipe metadata, active cooking step trackers, and dynamic timer pools.
* **Success Criteria**: FastAPI server running locally with complete OpenAPI documentation and operational Redis health checks.

### Phase 2: Asynchronous Low-Latency Audio Streaming (Ingestion)
* **Objective**: Establish a bi-directional WebSocket pipeline capable of handling raw audio chunks under noisy conditions.
* **Tasks**:
    * Implement a `/api/v1/stream` WebSocket endpoint in FastAPI to ingest binary linear16/PCM or Mu-law audio.
    * Build an asynchronous client wrapper for the `Deepgram` Real-Time Streaming SDK.
    * Enable advanced acoustic configuration parameters: noise termination, background suppression filters, and endpointing thresholds to isolate ambient kitchen noises (sizzling, running water).
    * Develop a non-blocking consumer loop that captures ASR transcription sentences and routes them to the main orchestrator.
* **Success Criteria**: Continuous transcription latency under 250ms from speech utterance to text token arrival at the backend.

### Phase 3: State Management & Tool Definition
* **Objective**: Expose system hooks to allow the language model to manipulate the physical context (timers, math conversions).
* **Tasks**:
    * Implement an abstract State Manager pattern to handle multi-tenant session persistence.
    * Develop core algorithmic skills as execution-ready Python functions: `set_kitchen_timer()`, `convert_units()`, `scale_recipe()`, and `Maps_steps()`.
    * Ensure all functions strictly mutate the localized `RecipeState` cache and handle validation edge cases safely (e.g., negative scaling factors or invalid metric units).
* **Success Criteria**: 100% test coverage on utility functions verifying atomic state mutations inside the Redis cache.

### Phase 4: Agent Core & LLM Tool Orchestration
* **Objective**: Wire the transcription pipeline to a reasoning engine capable of dynamic function calling and persona enforcement.
* **Tasks**:
    * Configure the Anthropic Claude API client using the streaming primitives (`anthropic.types.raw_message_stream_event`).
    * Inject the system prompt enforcing the concise, high-efficiency "Executive Sous-Chef" persona.
    * Map the Python skills defined in Phase 3 directly to Claude's `tools` array declaration matching the function schema definitions.
    * Implement a robust tool-execution loop: parse `tool_use` blocks from the LLM stream, execute the associated Python async task, return the execution result block to the conversation history, and continue streaming.
* **Success Criteria**: Accurate multi-turn context awareness where Claude executes a tool and speaks the result without breaking the WebSocket frame rate.

### Phase 5: Real-Time Audio Synthesis & Egress
* **Objective**: Transform generated text responses back into smooth, real-time spoken audio chunks.
* **Tasks**:
    * Integrate a streaming Text-to-Speech (TTS) client wrapper (using `Cartesia` or `ElevenLabs` WebSocket/gRPC APIs).
    * Pipe Claude's text tokens directly into the TTS engine chunk-by-chunk to maximize parallelization.
    * Package the outgoing binary audio chunks into outbound WebSocket text/binary frames target-formatted for client-side decoding.
* **Success Criteria**: Total systemic Glass-to-Glass (G2G) latency—measured from user speech termination to speaker audio playback—under 800ms.

### Phase 6: Client Interface & End-to-End Testing
* **Objective**: Build a lightweight web client and automated integration tests to lock down stability.
* **Tasks**:
    * Construct a single-page HTML5/JS interface capturing audio through the `AudioContext` API and streaming via native `WebSocket`.
    * Implement client-side audio frame queuing and processing to playback incoming chunks seamlessly without crackling or jitter.
    * Write a complete `pytest-asyncio` suite mocking deepgram and API dependencies to simulate network degradation, dropped packets, and abrupt user interruptions.
* **Success Criteria**: Seamless local browser execution passing 10/10 automated network resilience tests.