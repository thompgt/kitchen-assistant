# Kitchen Assistant — Target Architecture

## System Summary

A hands-free voice kitchen assistant with an "Executive Sous-Chef" persona. The browser captures microphone audio and streams it over a WebSocket to a FastAPI **session gateway**, which proxies it to the **Gemini Live API** (native audio-in/audio-out, server-side VAD, barge-in, function calling). Cooking tools and DuckDB recipe search (RAG) execute server-side inside the gateway; synthesized speech streams back to the browser.

Non-negotiables (see `CLAUDE.md`): Python 3.11+, fully async, <800ms glass-to-glass latency for conversational turns, Pydantic schemas as the single typed source of truth, concise professional persona.

## System Diagram

```
┌──────────────────────────┐        ┌────────────────────────────────────────────┐        ┌──────────────────────────┐
│   Browser client         │        │   FastAPI session gateway                  │        │   Gemini Live API        │
│   (static/index.html)    │        │   (app/main.py + app/live/gateway.py)      │        │   (google-genai SDK)     │
│                          │  WS    │                                            │  WS    │                          │
│  Mic ──AudioWorklet─────►│───────►│  /ws/voice/{session_id}                    │───────►│  client.aio.live.connect │
│  PCM16 mono 16 kHz       │ binary │   binary frame = PCM16 16k passthrough ───►│        │  built-in VAD, barge-in, │
│                          │ frames │                                            │        │  function calling        │
│  Speaker ◄──playback─────│◄───────│◄── PCM16 24 kHz audio passthrough ─────────│◄───────│                          │
│  PCM16 mono 24 kHz       │        │                                            │        │  audio out: PCM16 24 kHz │
│                          │  JSON  │  JSON frames: transcripts, timer events,   │        │  tool_call / interrupted │
│  Transcript + timer UI ◄─│◄───────│  interrupted, session status               │        │  / goAway / resumption   │
└──────────────────────────┘        │                                            │        └──────────────────────────┘
                                    │        │ tool_call events                   │
                                    │        ▼                                    │
                                    │  ┌──────────────────────┐                   │
                                    │  │ Tool registry        │                   │
                                    │  │ app/tools/registry.py│                   │
                                    │  └──┬───────────┬───────┘                   │
                                    │     ▼           ▼                           │
                                    │  cooking_tools  recipe_store (RAG)          │
                                    │     │           DuckDB data/recipes.db      │
                                    │     ▼           (vss/HNSW, gemini-          │
                                    │  StateManager    embedding-001, 3072-d)     │
                                    │  (in-memory │ Redis optional)               │
                                    │     ▲                                       │
                                    │  TimerEngine (asyncio tasks) ──proactive──► │  (inject expiry into Live session
                                    └────────────────────────────────────────────┘   + JSON event to browser)
```

**Audio formats at each hop** — no transcoding anywhere in the gateway, pure passthrough:

| Hop | Format |
|---|---|
| Browser → gateway | PCM16 mono 16 kHz little-endian, binary WS frames (~20–40 ms each) |
| Gateway → Gemini | `types.Blob(mime_type="audio/pcm;rate=16000")` via `session.send_realtime_input(audio=...)` |
| Gemini → gateway | PCM16 mono 24 kHz in `server_content` audio parts |
| Gateway → browser | Raw PCM16 24 kHz binary frames; client plays via `AudioContext({sampleRate: 24000})` |

## Component Responsibilities

### Session gateway — `app/live/gateway.py` (`LiveGateway`)

Owns one browser WS ↔ one Gemini Live session pairing per `session_id`. Replaces `orchestrator_v2.py` entirely — no audio buffering, no 3-second heuristic; VAD is Gemini's job. One gateway instance **per connection** (the current shared-orchestrator-across-all-connections design is a latent bug this fixes).

SDK entry points: `google.genai.Client(api_key=...)`, then `client.aio.live.connect(model=LIVE_MODEL, config=types.LiveConnectConfig(...))` with:

- `response_modalities=["AUDIO"]`
- `system_instruction` — Executive Sous-Chef prompt
- `tools=[types.Tool(function_declarations=[...])]` from the tool registry
- `input_audio_transcription={}` and `output_audio_transcription={}` — drives the browser transcript with no separate STT
- `session_resumption=types.SessionResumptionConfig(handle=...)`
- `context_window_compression=types.ContextWindowCompressionConfig(sliding_window=types.SlidingWindow())`

Two concurrent asyncio tasks per session:

1. **Uplink**: browser WS → `send_realtime_input`. Binary frames are audio
   (`send_realtime_input(audio=...)`); JSON `user.text` and `video.frame`
   envelopes map to `send_realtime_input(text=...)` and
   `send_realtime_input(video=types.Blob(...))` respectively — the latter
   feeds camera frames to the model for doneness checks ("is this done?").
2. **Downlink**: async-iterate `session.receive()` and route:
   - audio parts → binary frames to browser
   - `input_transcription` / `output_transcription` → JSON `transcript.user` / `transcript.agent`
   - `interrupted` flag → JSON `{"type":"interrupted"}` so the client flushes its playback queue (barge-in)
   - `tool_call` → tool registry dispatch → `session.send_tool_response(...)`
   - `session_resumption_update` → store the rolling handle
   - `go_away` → transparent reconnect with the stored handle

**Reconnection contract**: on GoAway or Live-side disconnect, reconnect with the resumption handle without dropping the browser WS. The browser only sees `{"type":"session.status","state":"reconnecting"|"ready"}`.

**Browser-facing WS protocol** (vendor-neutral by design — both the vanilla
client and the React HUD speak it unchanged):

| Frame | Direction | Meaning |
|---|---|---|
| binary | both | Audio (16 kHz up, 24 kHz down) |
| `user.text` | client → server | Typed input, used in place of the mic |
| `video.frame` | client → server | Base64 JPEG camera frame (`data`, `mime_type`), throttled client-side (~1.5s); forwarded via `send_realtime_input(video=...)` for doneness checks |
| `transcript.user` / `transcript.agent` | server → client | Live transcription of each side |
| `timer.update` / `timer.expired` | server → client | Timer lifecycle |
| `interrupted` | server → client | Flush playback queue (barge-in) |
| `session.status` | server → client | `ready` / `reconnecting` / `closed` |
| `state.snapshot` | server → client | Serialized `RecipeState` for UI |
| `error` | server → client | Structured error envelope |

### Tool registry — `app/tools/registry.py` (new) + `app/tools/cooking_tools.py` (kept)

A `ToolRegistry` mapping tool name → (`types.FunctionDeclaration`, async callable). Registered tools: `set_kitchen_timer`, `cancel_timer`, `list_timers`, `convert_units`, `scale_recipe`, `navigate_steps`, `search_recipes`, `load_recipe`.

**`session_id` is never a model-visible parameter.** The gateway injects it at dispatch time; declarations expose only user-meaningful args. Results return via `types.FunctionResponse(id=fc.id, name=fc.name, response={...})`.

Tools are pure async functions that read/write state exclusively through `StateManager` (injected), never module globals.

### State layer — `app/state_manager.py` (kept, becomes the single store)

`StateManager` with in-memory default and optional Redis (`USE_REDIS` / `REDIS_URL`). The module-level `_session_cache` + `_state_lock` in `cooking_tools.py` are deleted. `StateManager` gains a per-session `asyncio.Lock` and an atomic `async def update(session_id, mutator)` helper for safe read-modify-write.

Canonical model: `app/schemas.py` `RecipeState` (`recipe_metadata`, `current_step_index`, `active_timers`, `servings_multiplier`). `app/models.py` is deleted; imports re-point to `schemas.py`.

### RAG service — `app/services/recipe_store.py` (new)

Wraps DuckDB (`data/recipes.db`, moved out of `notebooks/`): `INSTALL vss; LOAD vss;`, embeddings via the new SDK `client.aio.models.embed_content(model="gemini-embedding-001", ...)` (migrating off deprecated `google.generativeai`).

- `search(query, k=3) -> list[RecipeSearchResult]` — `array_distance` over the `FLOAT[3072]` HNSW column
- `get_recipe(recipe_id) -> RecipeMetadata`

DuckDB is synchronous; calls run in `asyncio.to_thread`. The `load_recipe` tool hydrates `RecipeState.recipe_metadata` so `navigate_steps` has real steps to clamp against and read back.

### Timer engine — `app/services/timer_engine.py` (new)

Owns real `asyncio.create_task` countdowns keyed by `(session_id, timer_id)`; supports cancel; persists timer records in `RecipeState.active_timers` via StateManager. On expiry:

1. Sends `{"type":"timer.expired", ...}` JSON to the browser.
2. Injects a proactive turn into the Live session (`session.send_realtime_input(text=...)` or `send_client_content`) with a nudge like "Timer 'pasta' just finished — announce it", so the assistant *speaks* the expiry unprompted.

The gateway hands the engine a callback pair at session start; the engine never imports the gateway (no cycles). Tasks are cancelled on session disconnect.

### Browser clients

Two clients speak the same WS protocol; the gateway doesn't know or care which one is connected.

**Vanilla client — `static/`**, served via FastAPI `StaticFiles` at `/`. `index.html` + `app.js` + `pcm-worklet.js`. AudioWorklet captures mic at 16 kHz mono, Float32→Int16, ships ~20–40 ms binary frames. Playback: queue of 24 kHz PCM16 chunks into `AudioContext({sampleRate: 24000})`; on `interrupted`, flush the queue immediately. Camera toggle captures a JPEG frame every ~1.5s via canvas and sends it as `video.frame`. UI: transcript pane, active-timer chips with client-side countdown, connection status, camera preview. No framework, no build step.

**React HUD — `frontend/`** (Vite + TypeScript + Tailwind + Zustand, per `frontend_plan.md`), served at `/hud` via `StaticFiles(html=True)` once built (`npm run build`). Mirrors the vanilla client's audio/camera capture and playback logic in a `useVoiceSocket` hook, with a Zustand store mirroring `RecipeState`. Components: `StatusBar`, `InstructionCard`, `IngredientChecklist` (scaled by `servings_multiplier`), `ActiveTimerBoard` (circular countdown rings), `TranscriptPane`, `CameraPreview`, `MicButton`. Dark, high-contrast styling per the kitchen-specific design principles in `frontend_plan.md`.

## Design Decisions (ADRs)

**ADR-001 — Gemini Live API over modular Deepgram STT + LLM + Cartesia TTS.** One vendor and one WS hop instead of three services; built-in VAD, barge-in, and function calling. The old modular path never worked (`CartesiaTTS` import doesn't exist, no Deepgram SDK installed, TTS was a stub). Trade-off: vendor lock-in and preview-model churn, mitigated by keeping the browser protocol vendor-neutral.

**ADR-002 — Proxy through FastAPI instead of browser → Gemini direct.** The API key never reaches the client; tools must run server-side against server-held `RecipeState`; central place for resumption, logging, and future auth. Cost: one extra hop (~10–30 ms locally — inside budget).

**ADR-003 — Single state store = `StateManager` (in-memory default, Redis optional-off).** Today there are two uncoordinated stores and the one with the abstraction is unused. Consolidating restores the `CLAUDE.md` contract and makes tools testable via dependency injection. Redis stays optional until a deployment story needs it.

**ADR-004 — DuckDB + vss over a hosted vector DB.** Embedded single-file DB, zero ops, already built and populated (gemini-embedding-001, 3072-d, HNSW). At 4 recipes a vector service is pure overhead; revisit at >10k recipes or multi-writer needs. Caveat: HNSW persistence in DuckDB is experimental — brute-force `array_distance` is fine at this scale, so treat the index as optional.

**ADR-005 — Session-limit strategy.** Live connections are time-limited (~10–15 min). Enable `session_resumption` (store the rolling handle) + `context_window_compression` (sliding window); the gateway auto-reconnects on `GoAway` transparently. Kitchen sessions routinely exceed 15 minutes — this is a correctness requirement, not polish.

**ADR-006 — `schemas.py` is canonical; `models.py` deleted.** One Pydantic source of truth.

**ADR-007 — `google-genai` only; retire `google-generativeai`.** The Live API exists only in the new SDK (`client.aio.live`). The deprecated package remains only in scripts and `orchestrator_v2.py`, both rewritten or deleted by the workplan.

**ADR-008 — Vanilla JS client first, React HUD later.** Zero build tooling keeps the demo loop tight; the WS JSON protocol lets the HUD replace the page later without server changes. Done as of Phase 7: both clients ship and speak the identical protocol.

**ADR-009 — Shared-token auth, not user accounts.** The app is a single-deployment kitchen appliance (one container, LAN or personal use), not multi-tenant SaaS. `APP_AUTH_TOKEN` gates the WS route with one shared secret (`app/auth.py`); unset, access stays open for local/LAN dev — today's default behavior. A full accounts system (registration, per-user DBs, JWT) would be solving a problem this project doesn't have. Multi-*session* isolation already exists for free via `session_id`-keyed `StateManager` state.

**ADR-010 — Single container, Redis opt-in.** `Dockerfile` is a two-stage build (Node stage for the HUD, Python runtime for everything else); `docker-compose.yml` runs one `app` service against the in-memory `StateManager` by default. Redis (ADR-003) only matters once you run multiple replicas needing shared session state — wired as an opt-in `redis` compose profile rather than a hard dependency.

## Latency Budget (<800 ms glass-to-glass, conversational turns)

| Stage | Budget |
|---|---|
| Mic worklet framing | 20–40 ms |
| WS uplink (client → gateway) | 10–30 ms |
| Gateway forward | <5 ms |
| Gemini VAD end-of-speech → first audio chunk | 300–500 ms |
| WS downlink | 10–30 ms |
| Client jitter buffer + playback start | 40–80 ms |
| **Typical total** | **~450–700 ms** |

Turns requiring a tool round-trip add a dispatch (<10 ms for state tools; 50–300 ms for `search_recipes` embedding) plus a second model generation — tool turns **will** exceed 800 ms and that is accepted. The budget applies to plain conversational turns.

## Cleanup Map

| Path | Verdict | Replacement |
|---|---|---|
| `app/api/stream.py` | delete (never mounted; imports nonexistent `CartesiaTTS`) | `app/live/gateway.py` |
| `app/services/stt.py` | delete (Deepgram; SDK not installed, no key) | Gemini Live native audio-in |
| `app/services/tts.py` | delete (fake `[AUDIO: ...]` bytes) | Gemini Live native audio-out |
| `app/orchestrator.py` | delete (dead text loop; tool registration moves to registry) | `app/tools/registry.py` |
| `app/orchestrator_v2.py` | delete after Live migration (interim buffered hack) | `app/live/gateway.py` |
| `app/models.py` | delete, fold into `app/schemas.py` | `app/schemas.py` |
| `_session_cache` in `cooking_tools.py` | delete | `StateManager` |
| Tracked `app/venv/**`, `app/__pycache__/**` | purge from git, extend `.gitignore` | — |
| `notebooks/recipes.db` | move to `data/recipes.db` | accessed via `app/services/recipe_store.py` |
| `google-generativeai` dependency | remove once scripts migrate | `google-genai` |
| `frontend_plan.md` | keep as deferred backlog reference | — |

## Target Directory Tree

```
kitchen-assistant/
├── app/
│   ├── main.py               # FastAPI app: WS route, static mount, health
│   ├── schemas.py            # Canonical Pydantic models
│   ├── state_manager.py      # Single session store (in-memory | Redis)
│   ├── live/
│   │   └── gateway.py        # LiveGateway: browser WS ↔ Gemini Live proxy
│   ├── services/
│   │   ├── recipe_store.py   # DuckDB RAG: search / get_recipe
│   │   └── timer_engine.py   # asyncio countdowns + proactive expiry
│   └── tools/
│       ├── cooking_tools.py  # Tool implementations (stateless, injected state)
│       └── registry.py       # FunctionDeclarations + dispatch
├── static/                   # Vanilla JS voice client, served at /
│   ├── index.html
│   ├── app.js
│   └── pcm-worklet.js
├── frontend/                  # React/TS/Tailwind/Zustand HUD, served at /hud once built
│   └── src/
│       ├── hooks/useVoiceSocket.ts
│       ├── store/useSessionStore.ts
│       └── components/
├── data/
│   ├── recipes.db             # DuckDB (moved from notebooks/)
│   └── recipes_seed.json      # Source-of-truth recipe catalog
├── scripts/
│   ├── ingest_recipes.py     # Seed recipes (new SDK, new path)
│   ├── setup_vector_search.py
│   └── live_smoke.py         # Prerecorded-audio smoke test of the gateway
├── tests/                    # pytest + pytest-asyncio (fake Live backend)
├── notebooks/                # EDA / multimodal experiments
├── .github/workflows/ci.yml  # Lint + tests, frontend build, no API key required
├── Dockerfile                 # Multi-stage: HUD build + Python runtime
├── docker-compose.yml         # app service + optional redis profile
├── .env.example
├── ARCHITECTURE.md           # This file
└── workplan.md               # Authoritative phased roadmap
```

## Configuration

| Env var | Purpose | Default |
|---|---|---|
| `GOOGLE_API_KEY` | Gemini API access | required |
| `LIVE_MODEL` | Live-capable model id (preview names churn) | set at migration time |
| `USE_REDIS` | Enable Redis session store | `false` |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379` |
| `RECIPES_DB_PATH` | DuckDB recipe database | `data/recipes.db` |
| `APP_AUTH_TOKEN` | Shared token gating `/ws/voice/{session_id}` (ADR-009) | unset (open access) |
