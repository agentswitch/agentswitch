"""Codex CLI adapter — per-turn ``codex exec --json`` process."""

from __future__ import annotations

import shutil
from typing import AsyncIterator

from ..config import SessionConfig
from ..types import Event, EventType, Message, ToolCategory
from .._subprocess import spawn, read_jsonl, terminate
from .base import Provider

_TOOL_CATEGORIES: dict[str, ToolCategory] = {
    "shell": ToolCategory.BASH,
    "write_file": ToolCategory.FILE_EDIT,
    "read_file": ToolCategory.FILE_READ,
}


class CodexProvider(Provider):
    """Adapter for the Codex CLI (codex exec --json)."""

    name = "codex"

    def __init__(self) -> None:
        self._proc = None

    async def start(self, config: SessionConfig) -> None:
        # Codex uses per-turn processes; nothing to pre-start
        pass

    async def send(
        self,
        messages: list[Message],
        config: SessionConfig,
    ) -> AsyncIterator[Event]:
        prompt = self._build_prompt(messages)
        cmd = self._build_cmd(config, prompt)
        pcfg = config.get_provider_config(self.name)
        env: dict[str, str] = {}
        if pcfg.api_key:
            env["OPENAI_API_KEY"] = pcfg.api_key
        env.update(pcfg.env)

        self._proc = await spawn(cmd, env=env, cwd=config.workspace, stdin_pipe=False)
        yield Event(type=EventType.SESSION_START, provider=self.name)

        async for obj in read_jsonl(self._proc, timeout=pcfg.timeout):
            event = self._parse_event(obj)
            if event is not None:
                yield event
                if event.type in (EventType.TEXT_COMPLETE, EventType.RATE_LIMIT):
                    break

        await terminate(self._proc)
        self._proc = None

    async def stop(self) -> None:
        if self._proc is not None:
            await terminate(self._proc)
            self._proc = None

    async def is_available(self) -> bool:
        return shutil.which("codex") is not None

    def _build_prompt(self, messages: list[Message]) -> str:
        """Serialize transcript into a compound prompt for context transfer."""
        if len(messages) == 1:
            return messages[0].content
        parts: list[str] = []
        for msg in messages:
            prefix = "User" if msg.role == "user" else "Assistant"
            parts.append(f"[{prefix}]: {msg.content}")
        return "\n\n".join(parts)

    def _build_cmd(self, config: SessionConfig, prompt: str) -> list[str]:
        cmd = ["codex", "exec", "--json", "--skip-git-repo-check"]
        model = config.get_provider_config(self.name).model or config.model
        if model:
            cmd += ["--model", model]
        cmd += config.permission_flags(self.name)
        cmd += config.get_provider_config(self.name).extra_flags
        cmd.append(prompt)
        return cmd

    def _parse_event(self, obj: dict) -> Event | None:
        etype = obj.get("type", "")

        # Thread started — session init
        if etype == "thread.started":
            return Event(
                type=EventType.SESSION_START,
                provider=self.name,
                raw=obj,
            )

        # Item completed — can be reasoning, agent_message, or tool calls
        if etype == "item.completed":
            item = obj.get("item", {})
            item_type = item.get("type", "")
            text = item.get("text", "")

            if item_type == "agent_message":
                return Event(
                    type=EventType.TEXT_DELTA,
                    provider=self.name,
                    text=text,
                    raw=obj,
                )
            if item_type == "reasoning":
                return Event(
                    type=EventType.THINKING,
                    provider=self.name,
                    text=text,
                    raw=obj,
                )
            if item_type == "tool_call":
                tool_name = item.get("name", "shell")
                return Event(
                    type=EventType.TOOL_START,
                    provider=self.name,
                    tool_name=tool_name,
                    tool_category=_TOOL_CATEGORIES.get(tool_name, ToolCategory.OTHER),
                    raw=obj,
                )
            if item_type == "tool_output":
                return Event(
                    type=EventType.TOOL_OUTPUT,
                    provider=self.name,
                    text=text,
                    raw=obj,
                )

        # Turn completed — marks end of a full response turn
        if etype == "turn.completed":
            return Event(
                type=EventType.TEXT_COMPLETE,
                provider=self.name,
                raw=obj,
            )

        # Turn started
        if etype == "turn.started":
            return None  # skip, not useful

        # Error handling
        if etype == "error":
            msg = obj.get("message", obj.get("error", ""))
            if isinstance(msg, dict):
                msg = msg.get("message", str(msg))
            msg = str(msg)
            if "429" in msg or "rate_limit" in msg.lower():
                return Event(
                    type=EventType.RATE_LIMIT,
                    provider=self.name,
                    error_message=msg,
                    raw=obj,
                )
            return Event(
                type=EventType.ERROR,
                provider=self.name,
                error_message=msg,
                raw=obj,
            )

        return Event(type=EventType.RAW, provider=self.name, raw=obj)
