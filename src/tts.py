"""Streaming text-to-speech via ElevenLabs, with interruptible playback.

We spawn our own mpv/ffplay subprocess (rather than the SDK's ``stream()``
helper) so barge-in can kill playback instantly.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
from typing import Optional

from . import config


def _find_player() -> Optional[list[str]]:
    if shutil.which("mpv"):
        return ["mpv", "--no-terminal", "--really-quiet", "--no-cache", "--", "fd://0"]
    if shutil.which("ffplay"):
        return ["ffplay", "-autoexit", "-nodisp", "-loglevel", "quiet", "-"]
    return None


class Speaker:
    """Sentence-at-a-time streaming TTS.

    If no ELEVEN_API_KEY is configured (or no audio player is installed) the
    speaker runs muted — the app still works as a voice-in / text-out tool.
    """

    def __init__(
        self,
        voice_id: str = config.ELEVEN_VOICE_ID,
        model_id: str = config.ELEVEN_MODEL_ID,
        output_format: str = config.ELEVEN_OUTPUT_FORMAT,
    ):
        self._voice_id = voice_id
        self._model_id = model_id
        self._output_format = output_format
        self._player_cmd = _find_player()
        self._proc: Optional[subprocess.Popen] = None
        self._stop_requested = False

        self._client = None
        if config.ELEVEN_API_KEY:
            from elevenlabs.client import ElevenLabs

            self._client = ElevenLabs(api_key=config.ELEVEN_API_KEY)

    @property
    def enabled(self) -> bool:
        return self._client is not None and self._player_cmd is not None

    def describe_disabled_reason(self) -> str:
        if self._client is None:
            return "ELEVEN_API_KEY is not set — voice output disabled (text only)."
        if self._player_cmd is None:
            return (
                "Neither mpv nor ffplay found on PATH — voice output disabled (text only). "
                "Install one with: brew install mpv  (macOS) or apt install mpv (Linux)."
            )
        return ""

    async def speak(self, text: str) -> bool:
        """Speak one chunk of text. Returns False if interrupted or muted."""
        text = text.strip()
        if not text or not self.enabled:
            return False
        self._stop_requested = False
        return await asyncio.to_thread(self._speak_sync, text)

    def _speak_sync(self, text: str) -> bool:
        audio_iter = self._client.text_to_speech.stream(
            voice_id=self._voice_id,
            model_id=self._model_id,
            output_format=self._output_format,
            text=text,
        )
        proc = subprocess.Popen(
            self._player_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._proc = proc
        try:
            for chunk in audio_iter:
                if self._stop_requested:
                    return False
                if chunk:
                    proc.stdin.write(chunk)
            proc.stdin.close()
            proc.wait()
            return not self._stop_requested
        except (BrokenPipeError, OSError):
            return False
        finally:
            if proc.poll() is None and self._stop_requested:
                proc.kill()
            self._proc = None

    def stop(self) -> None:
        """Interrupt playback immediately (barge-in)."""
        self._stop_requested = True
        proc = self._proc
        if proc is not None and proc.poll() is None:
            proc.kill()
