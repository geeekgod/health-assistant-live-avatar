import os
import logging
from livekit.agents import tts, APIConnectionError
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, APIConnectOptions
from livekit.agents.utils import shortuuid
from google import genai
from google.genai import types

logger = logging.getLogger("liveavatar.gemini_tts")

class GeminiSynthesizeStream(tts.SynthesizeStream):
    def __init__(self, *, tts_instance, conn_options: APIConnectOptions) -> None:
        super().__init__(tts=tts_instance, conn_options=conn_options)
        self._tts = tts_instance

    async def _run(self, output_emitter: tts.AudioEmitter) -> None:
        text = ""
        async for msg in self._input_ch:
            if isinstance(msg, self._FlushSentinel):
                break
            text += msg

        if not text.strip():
            return
            
        try:
            response_stream = await self._tts._client.aio.models.generate_content_stream(
                model=self._tts._model,
                contents=text,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=self._tts._voice
                            )
                        )
                    )
                )
            )

            output_emitter.initialize(
                request_id=shortuuid(),
                sample_rate=24000,
                num_channels=1,
                mime_type="audio/pcm",
            )

            async for chunk in response_stream:
                if not chunk.candidates:
                    continue
                for part in chunk.candidates[0].content.parts:
                    if part.inline_data:
                        output_emitter.push(part.inline_data.data)

            output_emitter.flush()
        except Exception as e:
            logger.exception("Gemini TTS streaming failed")
            raise APIConnectionError() from e

class GeminiTTS(tts.TTS):
    def __init__(self, *, model: str = "gemini-3.1-flash-tts-preview", voice: str = "Aoede") -> None:
        super().__init__(
            capabilities=tts.TTSCapabilities(streaming=True),
            sample_rate=24000,
            num_channels=1,
        )
        self._model = model
        self._voice = voice
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY required for Gemini TTS")
        self._client = genai.Client(api_key=api_key, http_options={'api_version': 'v1alpha'})
        self._label = "google.genai.TTS"

    @property
    def model(self) -> str: return self._model

    @property
    def provider(self) -> str: return "google.genai"

    def synthesize(self, text: str, *, conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS) -> tts.ChunkedStream:
        return self._synthesize_with_stream(text, conn_options=conn_options)
        
    def stream(self, *, conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS) -> tts.SynthesizeStream:
        return GeminiSynthesizeStream(tts_instance=self, conn_options=conn_options)

    async def aclose(self) -> None: pass
