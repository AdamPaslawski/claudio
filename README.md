# Claude Code Voice Wrapper

Talk to Claude Code — hold a key, speak, and hear it answer while it works.

Local Whisper transcribes your speech, the Claude Agent SDK
runs Claude Code on your existing subscription (no API-key billing), and
ElevenLabs streams the response back as audio — sentence by sentence, as Claude
generates it. Push-to-talk with barge-in: press the hotkey while Claude is
speaking to cut it off and reply.

```
Mic → faster-whisper (local STT) → Claude Code (Agent SDK) → text processor → ElevenLabs TTS → Speaker
```

## Requirements

- Python 3.10+
- Claude Code installed and logged in (`claude` on your PATH)
- An [ElevenLabs](https://elevenlabs.io) API key (optional — without it the app
  runs voice-in / text-out)
- System packages:
  - **macOS:** `brew install portaudio ffmpeg mpv`
  - **Linux:** `apt install portaudio19-dev ffmpeg mpv`
  - **Windows:** `choco install ffmpeg mpv`

## Setup

```bash
uv sync                      # or: pip install -e .
cp .env.example .env         # then add your ELEVEN_API_KEY
```

## Install globally

To get `claude-voice` on your PATH and usable from **any** repo:

```bash
uv tool install --editable .           # from this checkout
mkdir -p ~/.config/claude-voice
cp .env ~/.config/claude-voice/env     # global config (API key, hotkey, ...)
```

Then `cd` into any project and run `claude-voice` — Claude Code operates on
whatever directory you launch from. Config resolution order: real environment
variables, then a `.env` in the current directory (per-project overrides),
then `~/.config/claude-voice/env`.

`--editable` means edits to this checkout take effect immediately; drop the
flag for a frozen install, and `uv tool upgrade claude-voice` after changes.

## Run (from this checkout)

```bash
uv run claude-voice          # or: python -m src.main
```

Hold **space** (configurable via `HOTKEY`), speak, release. The terminal shows
the full conversation — `[YOU]`, `[CLAUDE]`, `[TOOL]`, `[STATUS]` — while the
voice layer speaks a cleaned-up version (markdown stripped, paths spoken as
"source slash auth slash token dot t s", long code blocks summarized).

- **Barge-in:** press the hotkey while Claude is talking → TTS stops, you're
  immediately listening.
- **Permissions:** when Claude Code wants to run a tool (edit a file, run a
  command), the request is read aloud; say "yes" / "no" to approve or deny.

## Configuration

All via environment variables (or `.env`) — see [.env.example](.env.example):

| Variable | Default | Notes |
|---|---|---|
| `ELEVEN_API_KEY` | — | required for voice output |
| `WHISPER_MODEL` | `small` | `tiny`/`base`/`small`/`medium`/`large-v3` |
| `WHISPER_DEVICE` | `auto` | `cuda`, `cpu`, `auto` |
| `ELEVEN_VOICE_ID` | `JBFqnCBsd6RMkjVDRZzb` | any ElevenLabs voice |
| `ELEVEN_MODEL_ID` | `eleven_flash_v2_5` | lowest-latency model |
| `HOTKEY` | `space` | single char or pynput key name (`f8`, `ctrl_r`, ...) |
| `CODE_BLOCK_MODE` | `summarize` | `summarize` long blocks or `read` everything |

## Notes

- macOS will prompt for **Microphone** and **Input Monitoring / Accessibility**
  permissions (for the global hotkey) on first run — grant them to your
  terminal app.
- On Apple Silicon, faster-whisper is CPU-only; `small` is fast enough on
  M-series chips.
- The Agent SDK talks to Claude Code over stream-json stdio, so it uses your
  subscription auth and keeps multi-turn context across queries.
