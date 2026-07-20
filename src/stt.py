"""Speech-to-text via faster-whisper, running locally."""

from __future__ import annotations

import asyncio

import numpy as np

from . import config


class SpeechToText:
    def __init__(
        self,
        model_size: str = config.WHISPER_MODEL,
        device: str = config.WHISPER_DEVICE,
        compute_type: str = config.WHISPER_COMPUTE_TYPE,
    ):
        # Import here so the app can start (and fail with a clear message)
        # even if faster-whisper is missing.
        from faster_whisper import WhisperModel

        self._model = WhisperModel(model_size, device=device, compute_type=compute_type)

    def transcribe_sync(self, audio: np.ndarray) -> str:
        """Transcribe a float32 mono 16kHz buffer to text."""
        if audio.size == 0:
            return ""
        segments, _info = self._model.transcribe(
            audio,
            language="en",
            vad_filter=True,  # trim leading/trailing silence
            beam_size=5,
        )
        return " ".join(segment.text.strip() for segment in segments).strip()

    async def transcribe(self, audio: np.ndarray) -> str:
        """Async wrapper — inference runs in a worker thread."""
        return await asyncio.to_thread(self.transcribe_sync, audio)
