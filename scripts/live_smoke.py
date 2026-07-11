"""Phase 2 smoke test: one real round-trip through Gemini Live with tools.

Sends a request ("set a timer for 10 seconds" by default) as typed realtime
text — or streams a 16 kHz PCM16 mono WAV with --wav — using the exact same
LiveConnectConfig and ToolRegistry as the FastAPI gateway. Prints transcripts
and tool calls, and saves the spoken 24 kHz reply to a WAV file.

Usage:
    poetry run python scripts/live_smoke.py
    poetry run python scripts/live_smoke.py --wav ask_timer_16k.wav --out reply.wav
"""
import argparse
import asyncio
import os
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
from google import genai
from google.genai import types

from app.live.gateway import DEFAULT_LIVE_MODEL, INPUT_AUDIO_MIME, build_live_config
from app.state_manager import StateManager
from app.tools.registry import ToolRegistry

OUTPUT_SAMPLE_RATE = 24000
SESSION_ID = "smoke"


async def _stream_wav(session, wav_path: Path) -> None:
    with wave.open(str(wav_path), "rb") as wav:
        if wav.getframerate() != 16000 or wav.getnchannels() != 1 or wav.getsampwidth() != 2:
            raise SystemExit(f"{wav_path} must be 16 kHz mono PCM16.")
        chunk_frames = 16000 // 10  # 100 ms chunks, like the browser client will send
        while True:
            frames = wav.readframes(chunk_frames)
            if not frames:
                break
            await session.send_realtime_input(
                audio=types.Blob(data=frames, mime_type=INPUT_AUDIO_MIME)
            )
            await asyncio.sleep(0.1)


async def _collect(session, registry: ToolRegistry, audio: bytearray) -> None:
    """Drain receive() turns until one ends with reply audio collected.

    A tool call and its spoken follow-up can arrive within a single turn, or
    the follow-up can land in the next turn — either way, audio present at a
    turn boundary means the reply is complete.
    """
    while True:
        async for message in session.receive():
            if message.tool_call is not None:
                responses = []
                for call in message.tool_call.function_calls or []:
                    result = await registry.dispatch(
                        SESSION_ID, call.name, dict(call.args or {})
                    )
                    print(f"[tool] {call.name}({dict(call.args or {})}) -> {result}")
                    responses.append(
                        types.FunctionResponse(id=call.id, name=call.name, response=result)
                    )
                await session.send_tool_response(function_responses=responses)

            content = message.server_content
            if content is None:
                continue
            if content.input_transcription and content.input_transcription.text:
                print(f"[user]  {content.input_transcription.text}")
            if content.output_transcription and content.output_transcription.text:
                print(f"[agent] {content.output_transcription.text}")
            if content.model_turn is not None:
                for part in content.model_turn.parts or []:
                    if part.inline_data is not None and part.inline_data.data:
                        audio.extend(part.inline_data.data)

        if audio:
            return


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text", default="Set a timer for 10 seconds for the eggs.")
    parser.add_argument("--wav", type=Path, help="16 kHz PCM16 mono WAV to stream instead of text")
    parser.add_argument("--out", type=Path, default=Path("smoke_reply.wav"))
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()

    load_dotenv()
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise SystemExit("GOOGLE_API_KEY is not set (see .env.example).")
    model = os.getenv("LIVE_MODEL", DEFAULT_LIVE_MODEL)

    state_manager = StateManager(use_redis=False)
    registry = ToolRegistry(state_manager)
    client = genai.Client(api_key=api_key)
    audio = bytearray()

    print(f"Connecting to {model} ...")
    async with client.aio.live.connect(
        model=model, config=build_live_config(registry)
    ) as session:
        if args.wav:
            await _stream_wav(session, args.wav)
        else:
            print(f"[send]  {args.text}")
            await session.send_realtime_input(text=args.text)
        await asyncio.wait_for(_collect(session, registry, audio), timeout=args.timeout)

    with wave.open(str(args.out), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(OUTPUT_SAMPLE_RATE)
        out.writeframes(bytes(audio))
    seconds = len(audio) / (OUTPUT_SAMPLE_RATE * 2)
    print(f"Saved {seconds:.1f}s of audio to {args.out}")

    state = await state_manager.get_state(SESSION_ID)
    if state is not None and state.active_timers:
        for timer in state.active_timers.values():
            print(f"[state] timer '{timer.label}' {timer.duration_seconds}s -> persisted OK")
    else:
        print("[state] no timers persisted (tool was not called)")


if __name__ == "__main__":
    asyncio.run(main())
