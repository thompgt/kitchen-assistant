import os
from cartesia import Cartesia
from dotenv import load_dotenv
from typing import AsyncGenerator

load_dotenv()

class CartesiaTTS:
    def __init__(self):
        self.client = Cartesia(api_key=os.getenv("CARTESIA_API_KEY"))
        self.voice_id = "a0e69980-6b4d-424d-916c-a337c1a83e6b" # Example: British Chef or professional voice
        self.model_id = "sonic-english"
        self.output_format = {
            "container": "raw",
            "encoding": "pcm_s16le",
            "sample_rate": 16000,
        }

    async def stream_speech(self, text_stream: AsyncGenerator[str, None]) -> AsyncGenerator[bytes, None]:
        """
        Pipes a text stream into Cartesia and yields binary audio chunks.
        """
        # Create a streaming context
        ctx = self.client.tts.websocket()
        
        # We need to handle the streaming bi-directionally
        # Cartesia's SDK usually handles the websocket under the hood
        try:
            output = ctx.send(
                model_id=self.model_id,
                voice_id=self.voice_id,
                transcript=text_stream,
                output_format=self.output_format,
                stream=True
            )

            for chunk in output:
                yield chunk["audio"]
        finally:
            ctx.close()
