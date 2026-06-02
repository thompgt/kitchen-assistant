import os
import asyncio
from deepgram import (
    DeepgramClient,
    DeepgramClientOptions,
    LiveTranscriptionEvents,
    LiveOptions,
)
from dotenv import load_dotenv

load_dotenv()

class DeepgramSTT:
    def __init__(self, callback):
        self.client = DeepgramClient(os.getenv("DEEPGRAM_API_KEY"))
        self.callback = callback
        self.connection = None

    async def start(self):
        self.connection = self.client.listen.live.v("1")

        def on_message(self, result, **kwargs):
            sentence = result.channel.alternatives[0].transcript
            if len(sentence) > 0:
                print(f"STT Transcript: {sentence}")
                asyncio.run_coroutine_threadsafe(self.callback(sentence), asyncio.get_event_loop())

        def on_error(self, error, **kwargs):
            print(f"Deepgram Error: {error}")

        self.connection.on(LiveTranscriptionEvents.TranscriptResult, on_message)
        self.connection.on(LiveTranscriptionEvents.Metadata, lambda self, metadata, **kwargs: print(f"Metadata: {metadata}"))
        self.connection.on(LiveTranscriptionEvents.Error, on_error)

        options = LiveOptions(
            model="nova-2-kitchen", # Specialized model if available, otherwise nova-2
            language="en-US",
            smart_format=True,
            encoding="linear16",
            channels=1,
            sample_rate=16000,
            # Noise suppression and endpointing for kitchen environment
            no_delay=True,
            endpointing=300, # Faster endpointing
            vad_events=True,
            # Note: Deepgram handles background noise suppression automatically in Nova-2
        )

        if self.connection.start(options) is False:
            print("Failed to start Deepgram connection")
            return False
        return True

    async def send_audio(self, chunk):
        if self.connection:
            self.connection.send(chunk)

    async def stop(self):
        if self.connection:
            self.connection.finish()
