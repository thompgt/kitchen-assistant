# Kitchen Assistant — Engineering Workplan

> **This document supersedes** the previous 6-phase Deepgram/Claude/Cartesia plan (which the code diverged from after the Gemini migration), the ad-hoc "Phase 1 – Semantic RAG" numbering in git history, and the standalone `frontend_plan.md` (now a deferred backlog reference in Phase 7). Target architecture, component contracts, and ADRs live in [`ARCHITECTURE.md`](ARCHITECTURE.md) — phases below reference it rather than repeating it.

**Size legend:** S ≈ half day · M ≈ 1–2 days · L ≈ 2–4 days.
**Rule:** every phase ends in a demonstrably working state, committed in small steps.

## Dependency Graph

```
Phase 0 ──► Phase 1 ──► Phase 2 ──► ┬─► Phase 3 (browser client) ─┐
                                    ├─► Phase 4 (timer engine)   ─┼─► Phase 6 (tests + CI) ──► Phase 7 (backlog)
                                    └─► Phase 5 (RAG)            ─┘
```

Phases 3, 4, and 5 are independent of each other and can run in any order or in parallel. Phase 2 is the only phase with external-API discovery risk.

---

## Phase 0 — Repo Reconciliation & Hygiene (S/M)

**Goal:** one truthful codebase — nothing dead, nothing duplicated, secrets handled.

**Scope:**
- Delete dead pipeline: `app/api/stream.py`, `app/services/stt.py`, `app/services/tts.py`, `app/orchestrator.py` (per the Cleanup Map in ARCHITECTURE.md).
- Merge `app/models.py` into `app/schemas.py`; re-point imports in `app/state_manager.py` and `app/main.py`; delete `app/models.py`.
- Commit the currently-untracked `app/orchestrator_v2.py` and `scripts/test_voice_streaming.py` as explicitly interim (replaced in Phase 2).
- Purge tracked `app/venv/**` and `app/__pycache__/**` from git; extend `.gitignore` (`__pycache__/`, `*.pyc`, `.venv/`, `app/venv/`).
- Add `.env.example` (`GOOGLE_API_KEY=`, `LIVE_MODEL=`, `USE_REDIS=`, `REDIS_URL=`, `RECIPES_DB_PATH=`). Rotate the existing API key (it has lived in plaintext locally).
- Update `CLAUDE.md`: Poetry commands (not `pip install -r app/requirements.txt` / `venv_new`), current file map, pointer to ARCHITECTURE.md.

**Acceptance:** `poetry run uvicorn app.main:app` boots; `git ls-files` shows no venv/pycache/binary artifacts; all imports resolve with `models.py` gone; `CLAUDE.md` matches reality.

## Phase 1 — State Consolidation & Tool Hardening (M)

**Goal:** one state store; tools correct, injectable, and unit-tested.

**Scope:**
- `app/state_manager.py`: per-session `asyncio.Lock`, atomic `async def update(session_id, mutator)` helper, serialize `schemas.RecipeState`.
- `app/tools/cooking_tools.py`: drop module-level `_session_cache`/`_state_lock`, read/write through injected `StateManager`.
- Validation fixes: reject `multiplier <= 0` in `scale_recipe`; clamp `navigate_steps` to `[0, len(steps)-1]` with a helpful error when no recipe is loaded; reject zero/negative timer durations; expand `convert_units` (F↔C, kg, l, fl oz, alias/case handling).
- `scale_recipe` returns recomputed ingredient amounts (multiplier × base amounts from `recipe_metadata`), not just the stored factor.
- Bootstrap `tests/` — add `pytest` + `pytest-asyncio` as dev deps; `tests/test_cooking_tools.py`, `tests/test_state_manager.py`.

**Acceptance:** `poetry run pytest` green; `scale_recipe(0)` and out-of-bounds `navigate_steps` return structured errors; no module-level mutable state in tools.

## Phase 2 — Gemini Live Migration: Session Gateway + Tool Bridge (L) ⚠ riskiest phase

**Goal:** real-time audio in/out through Gemini Live with all tools callable; the buffered-audio hack dies.

**Scope:**
- New `app/live/gateway.py` — `LiveGateway` per ARCHITECTURE.md: uplink/downlink tasks, input/output transcription config, `interrupted`/`tool_call`/`session_resumption_update`/`go_away` handling, transparent reconnect. Design with a **connect-factory constructor arg** so Phase 6 can inject a fake Live backend.
- New `app/tools/registry.py` — `FunctionDeclaration`s for the tools + dispatch with server-side `session_id` injection.
- Rewrite the `/ws/voice/{session_id}` route in `app/main.py`: one gateway instance per connection (fixes the shared-orchestrator latent bug).
- Delete `app/orchestrator_v2.py`; replace `scripts/test_voice_streaming.py` with `scripts/live_smoke.py` (sends a prerecorded 16 kHz PCM WAV asking "set a timer for 10 seconds", saves returned 24 kHz audio to WAV, prints transcripts + tool-call log).
- Resolve at phase start: current Live-capable model id (`LIVE_MODEL` env var) and native-audio vs half-cascade choice (see Risks).

**Acceptance:** smoke script yields an audible spoken reply saved to WAV; a timer request triggers `set_kitchen_timer` visible in state; `interrupted` is forwarded on barge-in; session survives >10 min via the resumption handle (or the reconnect path is demonstrated with a forced disconnect).

## Phase 3 — Browser Client v1 (M)

**Goal:** hands-free demo in Chrome — talk, hear, see.

**Scope:**
- `static/index.html`, `static/app.js`, `static/pcm-worklet.js`; `StaticFiles` mount in `app/main.py`, `/` serves the page.
- Mic capture: `getUserMedia` → AudioWorklet → Int16 16 kHz binary frames.
- Playback queue at 24 kHz with flush-on-`interrupted` (barge-in).
- Transcript pane (user + agent), timer chips fed by `timer.update`/`state.snapshot`, connection status indicator.

**Acceptance:** full spoken conversation round-trip in the browser; interrupting the assistant mid-sentence stops playback promptly; transcripts render for both sides; works on localhost (mic requires localhost or HTTPS — document this).

## Phase 4 — Timer Engine + Proactive Expiry (M)

**Goal:** timers actually fire and the assistant announces them unprompted.

**Scope:**
- New `app/services/timer_engine.py`: asyncio countdown tasks keyed `(session_id, timer_id)`, cancel support, callback pair handed in by the gateway at session start (no import cycles).
- Wire into gateway session lifecycle: start/stop with session, cancel tasks on disconnect.
- `set_kitchen_timer` delegates to the engine; add `cancel_timer` and `list_timers` tool declarations.
- `tests/test_timer_engine.py` with short durations / fake clocks.

**Acceptance:** "set a timer for 15 seconds" → 15 s later the assistant *speaks* the expiry with no user prompt and the browser shows `timer.expired`; canceling works; disconnect leaves no orphaned tasks.

## Phase 5 — RAG Integration (M)

**Goal:** recipes searchable and loadable by voice; navigation operates on real steps.

**Scope:**
- Move `notebooks/recipes.db` → `data/recipes.db`.
- New `app/services/recipe_store.py`: DuckDB + vss, embeddings via new-SDK `client.aio.models.embed_content(model="gemini-embedding-001", ...)`, DuckDB calls in `asyncio.to_thread`.
- New tools `search_recipes(query)` and `load_recipe(recipe_id)` in `cooking_tools.py` + registry; `load_recipe` hydrates `RecipeState.recipe_metadata`; `navigate_steps` returns the actual instruction text of the current step.
- Update `scripts/ingest_recipes.py` + `scripts/setup_vector_search.py` to the new path and new SDK.
- `tests/test_recipe_store.py` against a fixture DB.

**Acceptance:** by voice — "find me a pasta recipe" → results spoken; "load the first one" then "what's step one?" → correct instruction; navigation clamps at the last step; scaling then reading ingredients shows scaled amounts.

## Phase 6 — Test Depth + CI (M)

**Goal:** regression safety without a live API key.

**Scope:**
- `tests/test_gateway.py`: WS integration tests using a **fake Live backend** (object mimicking the `client.aio.live.connect` async context manager and `receive()` stream, injected via the Phase 2 connect-factory seam). Cover tool dispatch, `interrupted` propagation, resumption-handle reconnect.
- FastAPI `TestClient`/`httpx` WS tests for the browser protocol.
- `.github/workflows/ci.yml`: Poetry install, ruff (or flake8) + pytest on push/PR — no secrets needed since Live is faked.

**Acceptance:** CI green on GitHub with no `GOOGLE_API_KEY` secret; gateway logic covered by fake-backend tests.

## Phase 7 — Backlog (complete)

- ~~React HUD per `frontend_plan.md`.~~ Done — `frontend/` (Vite/React/TS/Tailwind/
  Zustand), served at `/hud` when built; vanilla client at `/` untouched. Verified
  end-to-end (search → load → scale → set-timer) with a headless-browser driver.
- ~~Multimodal camera doneness checks (Live API video frames).~~ Done — a new
  `video.frame` client→server envelope (base64 JPEG, ~1.5s throttle) is forwarded
  by `LiveGateway` via `send_realtime_input(video=...)`; both clients have a
  Camera toggle + preview. Verified end-to-end with a headless-browser fake
  camera device — the model correctly describes the streamed frames.
- ~~Real recipe ingestion pipeline (beyond 4 hardcoded recipes; batch embeddings).~~ Done —
  catalog now lives in `data/recipes_seed.json` (16 recipes), `scripts/ingest_recipes.py`
  is idempotent and rebuilds the schema from scratch, `scripts/setup_vector_search.py`
  batch-embeds only rows missing a vector.
- ~~Auth / multi-user; deployment story (single container; Redis becomes relevant here).~~ Done —
  `APP_AUTH_TOKEN` shared-token gate on the WS route (`app/auth.py`, ADR-009; open access
  when unset); per-`session_id` state isolation already covers concurrent multi-user
  sessions with no extra work. `Dockerfile` (multi-stage: HUD build + Python runtime) and
  `docker-compose.yml` (app service + opt-in `redis` profile, ADR-010) — built, run, and
  health-checked locally, including verifying the auth gate flips on inside the container.

---

## Risks & Open Questions

1. **Live model naming churn (highest risk).** Live-capable model ids are preview-named and rotate (native-audio vs half-cascade variants). Mitigation: `LIVE_MODEL` env var; verify against current docs at Phase 2 start. Half-cascade has historically been more reliable *for function calling*; native audio sounds better. Start with whichever handles tools reliably — resolve empirically in Phase 2.
2. **Session duration/context limits.** ~10 min default connection; resumption + compression is designed in (ADR-005), but exact limits and the resumption handle's validity window need Phase 2 verification.
3. **Proactive timer injection semantics.** Injecting text mid-session while the user is silent may race with VAD state; `send_realtime_input(text=...)` vs `send_client_content` behavior needs a spike in Phase 4. Fallback: browser plays a local chime + shows the event; the assistant mentions it on the next turn.
4. **Tool-turn latency.** Function-calling turns are two model generations plus dispatch and will exceed 800 ms; accepted (see latency budget in ARCHITECTURE.md). `search_recipes` adds ~100–300 ms of embedding latency.
5. **Windows dev quirks.** asyncio Proactor loop with uvicorn + many tasks; DuckDB file locking if a notebook holds the DB open while the app runs (mitigated by moving to `data/` and read-only connections); write docs with `poetry run` so commands work in both PowerShell and bash.
6. **DuckDB HNSW experimental persistence.** Index may need rebuilding after DuckDB upgrades; brute-force is fine at 4 recipes, so the index is optional.
7. **Open — keep Redis?** Unused today; single-process in-memory suffices until deployment. Kept optional-off (ADR-003); cutting the dependency entirely is a valid simplification.
8. **Open — transcript fidelity.** Live input transcription reflects the audio Gemini heard, which can lag or differ slightly from what the user perceives. Acceptable for v1.
