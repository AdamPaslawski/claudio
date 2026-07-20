"""Claude Code interaction via the Claude Agent SDK.

``ClaudeSDKClient`` spawns Claude Code as a subprocess (stream-json over
stdio), maintains multi-turn context across ``query()`` calls, and uses the
existing Claude Code subscription auth — no API key billing.
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Awaitable, Callable, Optional

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    PermissionResultAllow,
    PermissionResultDeny,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolUseBlock,
)

# Callback: (tool_name, tool_input) -> approved?
PermissionCallback = Callable[[str, dict[str, Any]], Awaitable[bool]]


class ClaudeSession:
    """Thin async wrapper around ClaudeSDKClient for the voice loop.

    ``send()`` yields events as ``(kind, payload)`` tuples:
      - ("text", str)      — assistant text chunk (speak + print)
      - ("tool", str)      — a tool being used (print only)
      - ("result", str)    — final result metadata line (print only)
    """

    def __init__(self, on_permission: Optional[PermissionCallback] = None):
        # Force subscription auth: an exported ANTHROPIC_API_KEY would take
        # precedence over the claude.ai login and bill the API instead.
        options_kwargs: dict[str, Any] = {"env": {"ANTHROPIC_API_KEY": ""}}
        if on_permission is not None:

            async def can_use_tool(tool_name: str, tool_input: dict[str, Any], context: Any):
                approved = await on_permission(tool_name, tool_input)
                if approved:
                    return PermissionResultAllow()
                return PermissionResultDeny(message="Denied by voice command")

            options_kwargs["can_use_tool"] = can_use_tool

        self._options = ClaudeAgentOptions(**options_kwargs)
        self._client: Optional[ClaudeSDKClient] = None
        # "none" means claude.ai subscription login; anything else is API billing.
        self.api_key_source: Optional[str] = None

    async def __aenter__(self) -> "ClaudeSession":
        self._client = ClaudeSDKClient(options=self._options)
        await self._client.connect()
        return self

    async def __aexit__(self, *exc_info) -> None:
        if self._client is not None:
            await self._client.disconnect()
            self._client = None

    async def send(self, text: str) -> AsyncIterator[tuple[str, str]]:
        """Send a user turn and stream response events until the turn ends."""
        assert self._client is not None, "ClaudeSession must be used as an async context manager"
        await self._client.query(text)
        async for message in self._client.receive_response():
            if isinstance(message, SystemMessage) and message.subtype == "init":
                source = message.data.get("apiKeySource", "unknown")
                if source != self.api_key_source:
                    self.api_key_source = source
                    if source == "none":
                        yield ("auth", "claude.ai subscription (no API billing)")
                    else:
                        yield ("auth", f"WARNING: API key from {source} — turns are billed to the API!")
            elif isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        yield ("text", block.text)
                    elif isinstance(block, ToolUseBlock):
                        yield ("tool", block.name)
            elif isinstance(message, ResultMessage):
                info = f"turn done in {message.duration_ms}ms"
                cost = message.total_cost_usd
                # Only show cost when actually billing the API; on subscription
                # the SDK still reports a notional figure that isn't charged.
                if cost and self.api_key_source not in (None, "none"):
                    info += f" (${cost:.4f})"
                yield ("result", info)
