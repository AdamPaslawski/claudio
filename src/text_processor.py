"""Transform Claude's raw markdown/code output into voice-friendly text.

The terminal always shows the raw output; this module only shapes what gets
sent to TTS. Rules follow the design spec:

- code fences: read short blocks naturally, summarize long ones
- strip markdown (headings, bold, italics, bullets, inline code)
- file paths -> "source slash auth slash token dot t s"
- CLI flags -> "dash capital D", "dash dash save-dev"
- arrows / braces / brackets / parens spoken as words
- diff lines -> "Added: ..." / "Removed: ..."
"""

from __future__ import annotations

import re

from . import config

_CODE_FENCE_RE = re.compile(r"```([\w+-]*)[ \t]*\n(.*?)```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_HEADING_RE = re.compile(r"^#{1,6}\s+(.*)$", re.MULTILINE)
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
_ITALIC_RE = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)|(?<!_)_([^_\n]+)_(?!_)")
_BULLET_RE = re.compile(r"^\s*[-*+]\s+", re.MULTILINE)
_PATH_RE = re.compile(r"\b[\w.@~-]+(?:/[\w.@-]+)+\b")
_LONG_FLAG_RE = re.compile(r"(?<![\w-])--([\w-]+)")
_UPPER_FLAG_RE = re.compile(r"(?<![\w-])-([A-Z])\b")
_SHORT_FLAG_RE = re.compile(r"(?<![\w-])-([a-z])\b")

# File extensions spelled out letter-by-letter; others read as words.
_SPELLED_EXTENSIONS = {"ts", "js", "tsx", "jsx", "py", "md", "rb", "go", "rs", "sh", "css", "sql", "yml", "csv"}

_SYMBOLS = [
    ("=>", " arrow "),
    ("->", " arrow "),
    ("→", " arrow "),
    ("{}", " braces "),
    ("[]", " brackets "),
    ("()", " parens "),
]


def _speak_path(match: re.Match) -> str:
    path = match.group(0)
    parts = path.split("/")
    spoken_parts = []
    for part in parts:
        if "." in part.strip("."):
            stem, _, ext = part.rpartition(".")
            if ext.lower() in _SPELLED_EXTENSIONS:
                ext = " ".join(ext)
            part = f"{stem} dot {ext}" if stem else f"dot {ext}"
        spoken_parts.append(part)
    return " slash ".join(spoken_parts)


def _speak_flags(text: str) -> str:
    text = _LONG_FLAG_RE.sub(lambda m: f"dash dash {m.group(1)}", text)
    text = _UPPER_FLAG_RE.sub(lambda m: f"dash capital {m.group(1)}", text)
    text = _SHORT_FLAG_RE.sub(lambda m: f"dash {m.group(1)}", text)
    return text


def _speak_symbols(text: str) -> str:
    for raw, spoken in _SYMBOLS:
        text = text.replace(raw, spoken)
    return text


def _speak_code_line(line: str) -> str:
    stripped = line.strip()
    if not stripped:
        return ""
    # Diff lines
    if stripped.startswith("+") and not stripped.startswith("+++"):
        return "Added: " + _speak_code_line(stripped[1:])
    if stripped.startswith("-") and not stripped.startswith("---"):
        return "Removed: " + _speak_code_line(stripped[1:])

    text = stripped
    text = re.sub(r"\bdef\s+", "define ", text)
    text = _speak_symbols(text)
    text = _speak_flags(text)
    text = _PATH_RE.sub(_speak_path, text)
    # foo_bar -> "foo bar"
    text = re.sub(r"(?<=\w)_(?=\w)", " ", text)
    # call(args) -> "call of args"
    text = re.sub(r"(\w)\(", r"\1 of ", text)
    text = text.replace("(", " ").replace(")", " ")
    text = text.rstrip(":;")
    return re.sub(r"\s+", " ", text).strip()


def _first_definition(code: str) -> str | None:
    """Find a function/class name worth mentioning in a summary."""
    match = re.search(r"^\s*(?:def|class|function|const|func)\s+([\w$]+)", code, re.MULTILINE)
    if match:
        return match.group(1).replace("_", " ")
    return None


class TextForVoice:
    def __init__(self, code_block_mode: str = config.CODE_BLOCK_MODE):
        self.code_block_mode = code_block_mode

    def transform(self, raw_text: str) -> str:
        text = _CODE_FENCE_RE.sub(self._transform_code_block, raw_text)
        text = _INLINE_CODE_RE.sub(lambda m: " " + _speak_code_line(m.group(1)) + " ", text)
        text = _HEADING_RE.sub(lambda m: m.group(1).rstrip(".") + ".", text)
        text = _BOLD_RE.sub(lambda m: m.group(1) or m.group(2), text)
        text = _ITALIC_RE.sub(lambda m: m.group(1) or m.group(2), text)
        text = _BULLET_RE.sub("", text)
        text = _speak_symbols(text)
        text = _PATH_RE.sub(_speak_path, text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{2,}", "\n", text)
        return text.strip()

    def _transform_code_block(self, match: re.Match) -> str:
        lang = (match.group(1) or "").strip() or "code"
        code = match.group(2).strip("\n")
        lines = [ln for ln in code.splitlines() if ln.strip()]

        read_it = self.code_block_mode == "read" or len(lines) < config.SHORT_CODE_BLOCK_LINES
        if read_it:
            spoken = ". ".join(filter(None, (_speak_code_line(ln) for ln in lines)))
            return f" Here's a {lang} code block: {spoken}. "

        summary = f" There's a {len(lines)}-line {lang} code block here"
        name = _first_definition(code)
        if name:
            summary += f", defining {name}"
        summary += " — see the terminal for the full code. "
        return summary
