"""Capture the README screenshots from the real, running app.

Two phases, both optional:

  --record   Drive a real Gemini Live session through the real LiveGateway
             (needs GOOGLE_API_KEY) and save every browser-bound JSON envelope
             to assets/demo_session.json. Audio frames are dropped.

  (default)  Start uvicorn, then shoot with Playwright:
               * the vanilla client at /            — live backend, idle
               * the React HUD at /hud              — live backend, idle
               * the React HUD, session replayed    — the recorded envelopes
                 above are replayed into the page through a stubbed
                 window.WebSocket, so the components, the state shape and the
                 transcript text are all real; only the transport is faked.

Dev-only tooling: playwright is not a project dependency.

    python scripts/capture_screenshots.py --record
    python scripts/capture_screenshots.py
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

RECORDING = ROOT / "assets" / "demo_session.json"
SHOTS = ROOT / "assets" / "screenshots"
PORT = 8123
BASE = f"http://127.0.0.1:{PORT}"

PROMPTS = [
    "Find me a mushroom recipe and load it.",
    "Double it, then read me the current step.",
    "Set a nine minute timer for the risotto and a three minute one for the garlic.",
]


def _clean(envelopes: list[dict]) -> list[dict]:
    """Keep one ready frame, and stop at the first expiry so timers stay live."""
    out: list[dict] = []
    seen_ready = False
    for envelope in envelopes:
        if envelope["type"] == "timer.expired":
            break
        if envelope["type"] == "session.status":
            if envelope["status"] != "ready" or seen_ready:
                continue
            seen_ready = True
        out.append(envelope)
    return out


# --------------------------------------------------------------------------
# phase 1: record a real session
# --------------------------------------------------------------------------


async def _record() -> None:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    if not os.getenv("GOOGLE_API_KEY"):
        raise SystemExit("--record needs GOOGLE_API_KEY in .env")

    from app.live.gateway import LiveGateway
    from app.services.recipe_store import RecipeStore
    from app.services.timer_engine import TimerEngine
    from app.state_manager import StateManager
    from app.tools.registry import ToolRegistry

    class ScriptedWebSocket:
        """Browser stand-in: replays prompts, records browser-bound frames."""

        def __init__(self, prompts: list[str], gap: float) -> None:
            self._prompts = list(prompts)
            self._gap = gap
            self.envelopes: list[dict] = []
            self.last_frame_at = 0.0

        async def receive(self) -> dict:
            if self._prompts:
                await asyncio.sleep(self._gap)
                return {
                    "type": "websocket.receive",
                    "text": json.dumps({"type": "user.text", "text": self._prompts.pop(0)}),
                }
            await asyncio.sleep(3600)

        async def send_text(self, text: str) -> None:
            self.envelopes.append(json.loads(text))
            self.last_frame_at = asyncio.get_running_loop().time()

        async def send_bytes(self, data: bytes) -> None:  # audio: not recorded
            self.last_frame_at = asyncio.get_running_loop().time()

    state_manager = StateManager(use_redis=False)
    timer_engine = TimerEngine(state_manager)
    recipe_store = RecipeStore(db_path=str(ROOT / "data" / "recipes.db"))
    registry = ToolRegistry(state_manager, timer_engine=timer_engine, recipe_store=recipe_store)

    ws = ScriptedWebSocket(PROMPTS, gap=14.0)
    gateway = LiveGateway(
        websocket=ws,
        session_id="screenshot-demo",
        state_manager=state_manager,
        registry=registry,
        timer_engine=timer_engine,
    )
    task = asyncio.create_task(gateway.run())
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 14.0 * len(PROMPTS) + 30.0
    while loop.time() < deadline and not task.done():
        await asyncio.sleep(0.5)
        quiet = ws.last_frame_at and loop.time() - ws.last_frame_at > 5.0
        if not ws._prompts and quiet:
            break
    gateway._closing = True
    task.cancel()
    # Closing a Live session can block on its own handshake; never hang here.
    try:
        await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), timeout=10.0)
    except asyncio.TimeoutError:
        print("warning: gateway shutdown timed out; recording is still complete")
    timer_engine.unregister_session("screenshot-demo")

    envelopes = _clean(ws.envelopes)

    RECORDING.parent.mkdir(parents=True, exist_ok=True)
    RECORDING.write_text(
        json.dumps({"prompts": PROMPTS, "envelopes": envelopes}, indent=2), encoding="utf-8"
    )
    print(f"recorded {len(envelopes)} envelopes -> {RECORDING.relative_to(ROOT)}")


# --------------------------------------------------------------------------
# phase 2: shoot
# --------------------------------------------------------------------------

REPLAY_INIT = """
(() => {
  const recording = __RECORDING__;
  // Timer rings are driven off start_time; restamp recorded timers relative to
  // page load so the countdowns show real motion instead of a dead arc.
  const restamp = (envelope) => {
    if (envelope.type === 'state.snapshot') {
      for (const timer of Object.values(envelope.state.active_timers || {})) {
        const elapsed = Math.round(timer.duration_seconds * 0.35);
        // start_time is a naive local-time ISO string server-side, so shift
        // out the timezone offset before serialising.
        const offset = new Date().getTimezoneOffset() * 60000;
        timer.start_time = new Date(Date.now() - elapsed * 1000 - offset)
          .toISOString().replace('Z', '');
      }
    }
    return envelope;
  };
  class ReplayWebSocket {
    constructor(url) {
      this.url = url;
      this.readyState = 1;
      this.binaryType = 'arraybuffer';
      this.onmessage = null;
      this.onclose = null;
      this.onopen = null;
      setTimeout(() => this._play(), 60);
    }
    _play() {
      if (this.onopen) this.onopen({});
      let delay = 0;
      for (const frame of recording.frames) {
        delay += frame.gap;
        setTimeout(() => {
          if (this.onmessage) {
            this.onmessage({ data: JSON.stringify(restamp(frame.envelope)) });
          }
        }, delay);
      }
    }
    send() {}
    close() {}
  }
  window.WebSocket = ReplayWebSocket;
})();
"""


def _build_frames(recording: dict) -> list[dict]:
    """Turn recorded envelopes into replay frames, restamping timers to 'now'."""
    frames: list[dict] = []
    prompts = list(recording["prompts"])
    for envelope in recording["envelopes"]:
        if envelope["type"] == "transcript.user":
            continue  # the recorded run typed its prompts; we inject them below
        frames.append({"gap": 90, "envelope": envelope})

    # Put each prompt in front of the agent reply it produced, so the transcript
    # reads as the conversation it actually was.
    out: list[dict] = []
    pending = list(prompts)
    last_was_agent = True
    for frame in frames:
        if frame["envelope"]["type"] == "transcript.agent" and last_was_agent and pending:
            out.append(
                {"gap": 400, "envelope": {"type": "transcript.user", "text": pending.pop(0)}}
            )
            last_was_agent = False
        if frame["envelope"]["type"] != "transcript.agent":
            last_was_agent = True
        out.append(frame)
    return out


def _wait_for_health(timeout: float = 60.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{BASE}/health", timeout=2) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, OSError):
            time.sleep(0.5)
    raise SystemExit("backend did not come up")


def _shoot() -> None:
    from playwright.sync_api import sync_playwright

    SHOTS.mkdir(parents=True, exist_ok=True)
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT), "--host", "127.0.0.1"],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_health()
        recording = json.loads(RECORDING.read_text(encoding="utf-8")) if RECORDING.exists() else None

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            context = browser.new_context(viewport={"width": 1280, "height": 900})

            # 1. React HUD against the real backend, waiting for the Live
            #    session to come up (status flips connecting -> ready)
            page = context.new_page()
            page.goto(f"{BASE}/hud/", wait_until="networkidle")
            try:
                page.wait_for_function(
                    "document.body.innerText.toLowerCase().includes('ready')", timeout=25000
                )
            except Exception:
                print("warning: HUD never reached 'ready' (no API key?) - shooting as-is")
            page.wait_for_timeout(800)
            page.screenshot(path=str(SHOTS / "hud-idle.png"))
            page.close()

            # 2 + 3. Both clients with the recorded session replayed through a
            #        stubbed window.WebSocket.
            if recording is not None:
                frames = _build_frames(recording)
                init = REPLAY_INIT.replace("__RECORDING__", json.dumps({"frames": frames}))
                total = sum(frame["gap"] for frame in frames) + 2500
                for path, name in ((f"{BASE}/hud/", "hud-session"),
                                   (f"{BASE}/", "vanilla-client")):
                    page = context.new_page()
                    page.add_init_script(init)
                    page.goto(path, wait_until="domcontentloaded")
                    page.wait_for_timeout(total)
                    page.screenshot(path=str(SHOTS / f"{name}.png"))
                    page.close()

            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=15)
    for shot in sorted(SHOTS.glob("*.png")):
        print(f"wrote {shot.relative_to(ROOT)} ({shot.stat().st_size:,} bytes)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", action="store_true", help="re-record the demo session")
    parser.add_argument("--no-shoot", action="store_true", help="record only")
    args = parser.parse_args()

    if args.record:
        asyncio.run(_record())
    if not args.no_shoot:
        _shoot()


if __name__ == "__main__":
    main()
