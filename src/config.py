"""All configurable constants. Values come from the environment (a local
.env file is loaded first if present), with sensible defaults for a POC."""

from __future__ import annotations

import os
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader — no external dependency needed for a POC."""
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("'\"")
        os.environ.setdefault(key, value)


_load_dotenv(Path.cwd() / ".env")


# --- Speech-to-text (faster-whisper) ---
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "small")
WHISPER_DEVICE = os.environ.get("WHISPER_DEVICE", "auto")
WHISPER_COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE_TYPE", "auto")
SAMPLE_RATE = 16_000  # Whisper expects 16kHz mono
CHANNELS = 1

# --- Text-to-speech (ElevenLabs) ---
ELEVEN_API_KEY = os.environ.get("ELEVEN_API_KEY", "")
ELEVEN_VOICE_ID = os.environ.get("ELEVEN_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb")
ELEVEN_MODEL_ID = os.environ.get("ELEVEN_MODEL_ID", "eleven_flash_v2_5")
ELEVEN_OUTPUT_FORMAT = os.environ.get("ELEVEN_OUTPUT_FORMAT", "mp3_44100_128")

# --- Interaction ---
HOTKEY = os.environ.get("HOTKEY", "space")

# --- Output processing ---
CODE_BLOCK_MODE = os.environ.get("CODE_BLOCK_MODE", "summarize")  # "summarize" | "read"
SHORT_CODE_BLOCK_LINES = 5  # blocks shorter than this are read aloud even in summarize mode
