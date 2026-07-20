"""Microphone capture and push-to-talk hotkey handling.

The pynput listener runs in its own thread; press/release state is bridged
into asyncio via ``loop.call_soon_threadsafe``.
"""

from __future__ import annotations

import asyncio
from typing import Optional

import numpy as np
import sounddevice as sd
from pynput import keyboard

from . import config


def _resolve_hotkey(name: str):
    """Map a config string like "space" or "f8" or "x" to a pynput key."""
    name = name.strip().lower()
    if len(name) == 1:
        return keyboard.KeyCode.from_char(name)
    special = getattr(keyboard.Key, name, None)
    if special is None:
        raise ValueError(f"Unknown hotkey {name!r} — use a single character or a pynput key name like 'space', 'f8'")
    return special


class PushToTalk:
    """Hold-to-record microphone input keyed to a global hotkey.

    - ``record()`` waits for the hotkey to go down (returns immediately if it
      is already held, which is what makes barge-in flow into listening),
      captures audio until it is released, and returns a float32 mono buffer.
    - ``wait_for_press()`` resolves on the next key-down; used to detect
      barge-in while TTS is playing.
    """

    def __init__(self, hotkey: str = config.HOTKEY, sample_rate: int = config.SAMPLE_RATE):
        self._key = _resolve_hotkey(hotkey)
        self._sample_rate = sample_rate
        self._pressed = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._press_waiters: list[asyncio.Event] = []
        self._release_waiters: list[asyncio.Event] = []
        self._listener: Optional[keyboard.Listener] = None

    def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        self._listener.start()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    # --- pynput thread side ---

    def _matches(self, key) -> bool:
        if key == self._key:
            return True
        # Normalize character keys (pynput may report shifted/modified variants)
        return (
            isinstance(key, keyboard.KeyCode)
            and isinstance(self._key, keyboard.KeyCode)
            and key.char is not None
            and key.char.lower() == (self._key.char or "").lower()
        )

    def _on_press(self, key) -> None:
        if not self._matches(key) or self._pressed:
            return
        self._pressed = True
        self._notify(self._press_waiters)

    def _on_release(self, key) -> None:
        if not self._matches(key):
            return
        self._pressed = False
        self._notify(self._release_waiters)

    def _notify(self, waiters: list[asyncio.Event]) -> None:
        if self._loop is None:
            return
        for event in list(waiters):
            self._loop.call_soon_threadsafe(event.set)

    # --- asyncio side ---

    @property
    def is_pressed(self) -> bool:
        return self._pressed

    async def wait_for_press(self) -> None:
        if self._pressed:
            return
        event = asyncio.Event()
        self._press_waiters.append(event)
        try:
            await event.wait()
        finally:
            self._press_waiters.remove(event)

    async def _wait_for_release(self) -> None:
        if not self._pressed:
            return
        event = asyncio.Event()
        self._release_waiters.append(event)
        try:
            await event.wait()
        finally:
            self._release_waiters.remove(event)

    async def record(self) -> np.ndarray:
        """Wait for the hotkey, capture audio while held, return mono float32."""
        await self.wait_for_press()

        frames: list[np.ndarray] = []

        def callback(indata, _frames, _time, status):
            if status:
                pass  # over/underruns are tolerable for push-to-talk
            frames.append(indata.copy())

        stream = sd.InputStream(
            samplerate=self._sample_rate,
            channels=config.CHANNELS,
            dtype="float32",
            callback=callback,
        )
        with stream:
            await self._wait_for_release()

        if not frames:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(frames).flatten()
