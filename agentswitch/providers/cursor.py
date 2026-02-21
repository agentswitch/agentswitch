"""Cursor Agent CLI adapter — per-turn process with stream-json output."""

from __future__ import annotations

import shutil
from typing import AsyncIterator

from ..config import SessionConfig
from ..types import Event, EventType, Message, ToolCategory
from .._subprocess import spawn, read_jsonl, terminate
from .base import Provider


class CursorProvider(Provider):
    """Adapter for the Cursor Agent CLI (cursor-agent)."""

    name = "cursor"

    def __init__(self) -> None:
        self._proc = None
        self._session_id: str = ""

    async def start(self, config: SessionConfig) -> None:
        # Cursor uses per-turn processes; nothing to pre-start
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
            env["CURSOR_API_KEY"] = pcfg.api_key
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
        self._session_id = ""

    async def is_available(self) -> bool:
        return shutil.which("cursor-agent") is not None

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
        cmd = [
            "cursor-agent",
            "-p",
            "--output-format", "stream-json",
        ]
        model = config.get_provider_config(self.name).model or config.model
        if model:
            cmd += ["--model", model]
        cmd += config.permission_flags(self.name)
        cmd += config.get_provider_config(self.name).extra_flags
        cmd.append(prompt)
        return cmd

    def _parse_event(self, obj: dict) -> Event | None:
        etype = obj.get("type", "")

        # System init — capture session_id
        if etype == "system":
            self._session_id = obj.get("session_id", self._session_id)
            return Event(type=EventType.SESSION_START, provider=self.name, raw=obj)

        # Assistant message — contains the response content blocks
        if etype == "assistant":
            message = obj.get("message", {})
            content_blocks = message.get("content", [])
            texts: list[str] = []
            for block in content_blocks:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        texts.append(block.get("text", ""))
                    elif block.get("type") == "tool_use":
                        tool_name = block.get("name", "")
                        return Event(
                            type=EventType.TOOL_START,
                            provider=self.name,
                            tool_name=tool_name,
                            tool_category=ToolCategory.OTHER,
                            raw=obj,
                        )
            if texts:
                return Event(
                    type=EventType.TEXT_DELTA,
                    provider=self.name,
                    text="".join(texts),
                    raw=obj,
                )

        # Thinking events
        if etype == "thinking":
            return Event(
                type=EventType.THINKING,
                provider=self.name,
                text=obj.get("content", ""),
                raw=obj,
            )

        # Tool call events
        if etype == "tool_call":
            status = obj.get("status", "")
            tool_name = obj.get("name", "")
            if status == "started":
                return Event(
                    type=EventType.TOOL_START,
                    provider=self.name,
                    tool_name=tool_name,
                    tool_category=ToolCategory.OTHER,
                    raw=obj,
                )
            if status == "completed":
                return Event(
                    type=EventType.TOOL_END,
                    provider=self.name,
                    tool_name=tool_name,
                    text=obj.get("output", ""),
                    raw=obj,
                )

        # Result — turn complete
        if etype == "result":
            text = obj.get("result", "")
            if isinstance(text, dict):
                text = text.get("text", "")
            return Event(
                type=EventType.TEXT_COMPLETE,
                provider=self.name,
                text=str(text),
                raw=obj,
            )

        # Errors
        if etype == "error":
            msg = obj.get("message", obj.get("error", ""))
            if isinstance(msg, dict):
                msg = str(msg)
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

        # Skip user echo events
        if etype == "user":
            return None

        return Event(type=EventType.RAW, provider=self.name, raw=obj)
