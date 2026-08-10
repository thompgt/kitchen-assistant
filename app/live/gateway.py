"""LiveGateway: bridges one browser WebSocket to one Gemini Live session.

Audio is pure passthrough (PCM16 mono: 16 kHz uplink, 24 kHz downlink — no
transcoding). JSON envelopes carry everything else; the browser protocol is
documented in ARCHITECTURE.md.

The Gemini connection is produced by a connect factory so tests can inject a
fake Live backend (Phase 6) instead of the real `client.aio.live.connect`.
"""
import asyncio
import base64
import json
import logging
import os
import random
from typing import Any, AsyncContextManager, Callable, Dict, Optional

from fastapi import WebSocket
from google import genai
from google.genai import types

from ..schemas import KitchenTimer
from ..services.timer_engine import TimerEngine
from ..state_manager import StateManager
from ..tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

DEFAULT_LIVE_MODEL = "gemini-3.1-flash-live-preview"
INPUT_AUDIO_MIME = "audio/pcm;rate=16000"

# Reconnect policy. A connection shorter than HEALTHY_CONNECTION_SECONDS never
# really got going (quota exhausted, bad model id: accept-then-close), so those
# back off exponentially with jitter instead of spinning. Anything longer is a
# normal GoAway rotation and resets the counter.
HEALTHY_CONNECTION_SECONDS = 5.0
RECONNECT_BASE_DELAY_SECONDS = 0.5
RECONNECT_MAX_DELAY_SECONDS = 30.0
MAX_CONSECUTIVE_RECONNECTS = 6
RECONNECT_FAILED_CLOSE_CODE = 1011

SYSTEM_INSTRUCTION = (
    "You are an Executive Sous-Chef voice assistant for a busy kitchen. "
    "Be concise, professional, and efficiency-focused — no conversational "
    "filler. Help the chef manage recipes, timers, unit conversions, and "
    "step-by-step navigation using your tools. Announce tool results briefly. "
    "If the chef shares their camera, use it to answer doneness questions "
    "('is this done?', 'is it browned enough?') from what you see — describe "
    "what you observe and give a direct verdict."
)

# A connect factory returns the async context manager normally produced by
# `client.aio.live.connect(...)`.
ConnectFactory = Callable[[], AsyncContextManager[Any]]


def build_live_config(
    registry: ToolRegistry, resumption_handle: Optional[str] = None
) -> types.LiveConnectConfig:
    """Live session config shared by the gateway and scripts/live_smoke.py."""
    return types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=SYSTEM_INSTRUCTION,
        tools=registry.live_tools(),
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        session_resumption=types.SessionResumptionConfig(handle=resumption_handle),
        context_window_compression=types.ContextWindowCompressionConfig(
            sliding_window=types.SlidingWindow()
        ),
    )


class LiveGateway:
    """One instance per browser connection; owns the Gemini Live session."""

    def __init__(
        self,
        websocket: WebSocket,
        session_id: str,
        state_manager: StateManager,
        registry: ToolRegistry,
        connect_factory: Optional[ConnectFactory] = None,
        model: Optional[str] = None,
        timer_engine: Optional[TimerEngine] = None,
    ):
        self._ws = websocket
        self._session_id = session_id
        self._state_manager = state_manager
        self._registry = registry
        self._model = model or os.getenv("LIVE_MODEL", DEFAULT_LIVE_MODEL)
        self._connect_factory = connect_factory or self._default_connect_factory
        self._timer_engine = timer_engine
        self._resumption_handle: Optional[str] = None
        self._closing = False
        self._session: Optional[Any] = None

    # -- connection ---------------------------------------------------------

    def _default_connect_factory(self) -> AsyncContextManager[Any]:
        client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
        return client.aio.live.connect(model=self._model, config=self._build_config())

    def _build_config(self) -> types.LiveConnectConfig:
        return build_live_config(self._registry, self._resumption_handle)

    async def run(self) -> None:
        """Proxy until the browser disconnects; reconnect to Gemini on GoAway.

        Each reconnect passes the last session-resumption handle, so the model
        keeps its conversation context across the ~10-minute Live connection
        limit (ADR-005).
        """
        if self._timer_engine is not None:
            self._timer_engine.register_session(self._session_id, self._on_timer_expired)
        consecutive_short_connections = 0
        try:
            while not self._closing:
                connected_at = asyncio.get_running_loop().time()
                async with self._connect_factory() as session:
                    self._session = session
                    await self._send_json({"type": "session.status", "status": "ready"})
                    uplink = asyncio.create_task(self._uplink(session))
                    downlink = asyncio.create_task(self._downlink(session))
                    done, pending = await asyncio.wait(
                        {uplink, downlink}, return_when=asyncio.FIRST_COMPLETED
                    )
                    for task in pending:
                        task.cancel()
                    await asyncio.gather(*pending, return_exceptions=True)
                    for task in done:
                        task.result()  # surface uplink/downlink errors
                self._session = None
                if self._closing:
                    continue

                elapsed = asyncio.get_running_loop().time() - connected_at
                if elapsed >= HEALTHY_CONNECTION_SECONDS:
                    consecutive_short_connections = 0
                else:
                    consecutive_short_connections += 1

                if consecutive_short_connections > MAX_CONSECUTIVE_RECONNECTS:
                    logger.error(
                        "session %s: %d consecutive short-lived Live connections, giving up",
                        self._session_id,
                        consecutive_short_connections,
                    )
                    await self._send_json(
                        {
                            "type": "error",
                            "message": "Lost the Gemini Live connection and could not "
                            "re-establish it. Reload to try again.",
                        }
                    )
                    await self._ws.close(
                        code=RECONNECT_FAILED_CLOSE_CODE,
                        reason="Live reconnect attempts exhausted",
                    )
                    self._closing = True
                    continue

                delay = self._reconnect_delay(consecutive_short_connections)
                logger.info(
                    "session %s: Live connection ended after %.1fs, reconnecting in %.2fs "
                    "(handle=%s)",
                    self._session_id,
                    elapsed,
                    delay,
                    "yes" if self._resumption_handle else "no",
                )
                await self._send_json({"type": "session.status", "status": "reconnecting"})
                if delay:
                    await asyncio.sleep(delay)
        finally:
            if self._timer_engine is not None:
                self._timer_engine.unregister_session(self._session_id)

    @staticmethod
    def _reconnect_delay(consecutive_short_connections: int) -> float:
        """Full-jitter exponential backoff; 0 after a healthy connection."""
        if consecutive_short_connections <= 0:
            return 0.0
        ceiling = min(
            RECONNECT_BASE_DELAY_SECONDS * 2 ** (consecutive_short_connections - 1),
            RECONNECT_MAX_DELAY_SECONDS,
        )
        return random.uniform(0.0, ceiling)

    # -- browser -> Gemini ----------------------------------------------------

    async def _uplink(self, session: Any) -> None:
        while True:
            message = await self._ws.receive()
            if message.get("type") == "websocket.disconnect":
                self._closing = True
                return

            data = message.get("bytes")
            if data is not None:
                await session.send_realtime_input(
                    audio=types.Blob(data=data, mime_type=INPUT_AUDIO_MIME)
                )
                continue

            text = message.get("text")
            if text is not None:
                try:
                    envelope = json.loads(text)
                    if not isinstance(envelope, dict):
                        raise ValueError("envelope must be a JSON object")
                    envelope_type = envelope.get("type")
                    if envelope_type == "user.text":
                        await session.send_realtime_input(text=envelope["text"])
                    elif envelope_type == "video.frame":
                        await session.send_realtime_input(
                            video=types.Blob(
                                data=base64.b64decode(envelope["data"], validate=True),
                                mime_type=envelope.get("mime_type", "image/jpeg"),
                            )
                        )
                    else:
                        await self._send_json(
                            {
                                "type": "error",
                                "message": f"Unknown client envelope '{envelope_type}'.",
                            }
                        )
                except (ValueError, KeyError, TypeError) as exc:
                    # binascii.Error and json.JSONDecodeError both subclass ValueError.
                    # A malformed frame must not abort the cooking session.
                    logger.warning(
                        "session %s: discarding malformed client frame: %s",
                        self._session_id,
                        exc,
                    )
                    await self._send_json(
                        {"type": "error", "message": f"Malformed client envelope: {exc}"}
                    )

    # -- Gemini -> browser ----------------------------------------------------

    async def _downlink(self, session: Any) -> None:
        async for message in session.receive():
            update = message.session_resumption_update
            if update is not None and update.resumable and update.new_handle:
                self._resumption_handle = update.new_handle

            if message.go_away is not None:
                logger.info(
                    "session %s: GoAway (time_left=%s)",
                    self._session_id,
                    message.go_away.time_left,
                )
                return  # run() reconnects with the resumption handle

            if message.tool_call is not None:
                await self._handle_tool_call(session, message.tool_call)

            content = message.server_content
            if content is None:
                continue
            if content.interrupted:
                await self._send_json({"type": "interrupted"})
            if content.input_transcription and content.input_transcription.text:
                await self._send_json(
                    {"type": "transcript.user", "text": content.input_transcription.text}
                )
            if content.output_transcription and content.output_transcription.text:
                await self._send_json(
                    {"type": "transcript.agent", "text": content.output_transcription.text}
                )
            if content.model_turn is not None:
                for part in content.model_turn.parts or []:
                    if part.inline_data is not None and part.inline_data.data:
                        await self._ws.send_bytes(part.inline_data.data)
        # receive() ended without GoAway: run() reconnects unless the browser is gone.

    async def _handle_tool_call(self, session: Any, tool_call: types.LiveServerToolCall) -> None:
        responses = []
        for call in tool_call.function_calls or []:
            if call.name is None:
                continue
            result = await self._registry.dispatch(
                self._session_id, call.name, dict(call.args or {})
            )
            logger.info(
                "session %s: tool %s(%s) -> %s",
                self._session_id,
                call.name,
                call.args,
                result.get("status"),
            )
            responses.append(
                types.FunctionResponse(id=call.id, name=call.name, response=result)
            )
        if responses:
            await session.send_tool_response(function_responses=responses)
            await self._send_state_snapshot()

    # -- timer engine -> browser + model ---------------------------------------

    async def _on_timer_expired(self, timer: KitchenTimer) -> None:
        """Registered with TimerEngine; fires even when the model is idle."""
        await self._send_json(
            {"type": "timer.expired", "timer_id": timer.id, "label": timer.label}
        )
        await self._send_state_snapshot()
        if self._session is not None:
            await self._session.send_realtime_input(
                text=(
                    f"[System: the '{timer.label}' timer just expired. "
                    "Announce this to the chef now.]"
                )
            )

    async def _send_state_snapshot(self) -> None:
        state = await self._state_manager.get_state(self._session_id)
        if state is not None:
            await self._send_json(
                {"type": "state.snapshot", "state": state.model_dump(mode="json")}
            )

    async def _send_json(self, envelope: Dict[str, Any]) -> None:
        await self._ws.send_text(json.dumps(envelope))
