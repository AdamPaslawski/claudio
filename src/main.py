"""Entry point: the voice conversation loop.

State machine:
    IDLE -> (hotkey press) -> LISTENING -> (release) -> TRANSCRIBING
         -> SENDING -> SPEAKING -> IDLE
    SPEAKING -> (hotkey press) -> barge-in: stop TTS, go straight to LISTENING
"""

from __future__ import annotations

import asyncio
import re
import sys

from . import config
from .audio import PushToTalk
from .claude_interface import ClaudeSession
from .stt import SpeechToText
from .text_processor import TextForVoice
from .tts import Speaker

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_YES_RE = re.compile(r"\b(yes|yeah|yep|sure|approve|approved|go ahead|do it|okay|ok)\b", re.IGNORECASE)


def status(message: str) -> None:
    print(f"[STATUS]: {message}", flush=True)


def _drain_sentences(buffer: str) -> tuple[list[str], str]:
    """Split off complete sentences; return (ready_sentences, remainder)."""
    parts = _SENTENCE_SPLIT_RE.split(buffer)
    if len(parts) <= 1:
        return [], buffer
    return [p for p in parts[:-1] if p.strip()], parts[-1]


class VoiceWrapper:
    def __init__(self):
        self.recorder = PushToTalk()
        self.speaker = Speaker()
        self.processor = TextForVoice()
        self.stt: SpeechToText | None = None
        self._interrupted = False

    # --- voice primitives ---

    async def listen(self) -> str:
        """Push-to-talk capture + transcription. Returns "" for silence."""
        status(f"Hold [{config.HOTKEY}] and speak...")
        audio = await self.recorder.record()
        status("Transcribing...")
        assert self.stt is not None
        return await self.stt.transcribe(audio)

    async def confirm_permission(self, tool_name: str, tool_input: dict) -> bool:
        """Read a permission request aloud; listen for a spoken yes/no."""
        detail = str(tool_input)
        if len(detail) > 200:
            detail = detail[:200] + "..."
        print(f"[PERMISSION]: Claude wants to use {tool_name}: {detail}")
        await self.speaker.speak(
            f"Claude wants to use the {tool_name} tool. Say yes to approve, or no to deny."
        )
        answer = await self.listen()
        print(f"[YOU]: {answer}")
        approved = bool(_YES_RE.search(answer))
        status("Approved." if approved else "Denied.")
        return approved

    async def _speak_or_barge(self, sentence: str) -> bool:
        """Speak one sentence, racing against a hotkey press.

        Returns True if the user barged in (TTS stopped).
        """
        if self._interrupted or not self.speaker.enabled:
            return self._interrupted
        speak_task = asyncio.create_task(self.speaker.speak(sentence))
        barge_task = asyncio.create_task(self.recorder.wait_for_press())
        done, _pending = await asyncio.wait(
            {speak_task, barge_task}, return_when=asyncio.FIRST_COMPLETED
        )
        if barge_task in done:
            self._interrupted = True
            self.speaker.stop()
            await speak_task  # let the playback thread wind down
        else:
            barge_task.cancel()
        return self._interrupted

    # --- one conversational turn ---

    async def run_turn(self, claude: ClaudeSession, user_text: str) -> None:
        status("Sending to Claude Code...")
        self._interrupted = False
        pending = ""

        async for kind, payload in claude.send(user_text):
            if kind == "text":
                print(f"[CLAUDE]: {payload}")
                if self._interrupted:
                    continue  # keep draining the stream, but stay silent
                status("Speaking...")
                pending += (" " if pending else "") + self.processor.transform(payload)
                sentences, pending = _drain_sentences(pending)
                for sentence in sentences:
                    if await self._speak_or_barge(sentence):
                        break
            elif kind == "tool":
                print(f"[TOOL]: {payload}")
            elif kind == "result":
                print(f"[STATUS]: {payload}")

        if pending.strip() and not self._interrupted:
            await self._speak_or_barge(pending.strip())

        if self._interrupted:
            status("Interrupted — listening.")

    # --- main loop ---

    async def run(self) -> None:
        status(f"Loading Whisper model '{config.WHISPER_MODEL}' (first run downloads it)...")
        self.stt = await asyncio.to_thread(SpeechToText)

        if not self.speaker.enabled:
            print(f"[WARN]: {self.speaker.describe_disabled_reason()}")

        self.recorder.start()
        try:
            async with ClaudeSession(on_permission=self.confirm_permission) as claude:
                print()
                print(f"Voice wrapper ready. Hold [{config.HOTKEY}] to speak, Ctrl+C to quit.")
                print()
                while True:
                    text = await self.listen()
                    if not text.strip():
                        status("Heard nothing — try again.")
                        continue
                    print(f"[YOU]: {text}")
                    await self.run_turn(claude, text)
        finally:
            self.speaker.stop()
            self.recorder.stop()


async def main() -> None:
    wrapper = VoiceWrapper()
    await wrapper.run()


def cli() -> None:
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBye.")
        sys.exit(0)


if __name__ == "__main__":
    cli()
