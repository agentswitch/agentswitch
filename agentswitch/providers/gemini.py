"""Gemini CLI adapter — per-turn ``gemini -p`` process with stream-json output."""

from __future__ import annotations

import shutil
from typing import AsyncIterator

from ..config import SessionConfig
from ..types import Event, EventType, Message, ToolCategory
from .._subprocess import spawn, read_jsonl, terminate
from .base import Provider

_TOOL_CATEGORIES: dict[str, ToolCategory] = {
    "shell": ToolCategory.BASH,
    "edit_file": ToolCategory.FILE_EDIT,
    "write_file": ToolCategory.FILE_EDIT,
    "read_file": ToolCategory.FILE_READ,
    "search_files": ToolCategory.SEARCH,
    "web_search": ToolCategory.WEB,
}


class GeminiProvider(Provider):
    """Adapter for the Gemini CLI (gemini)."""

    name = "gemini"

    def __init__(self) -> None:
        self._proc = None
        self._session_id: str = ""

    async def start(self, config: SessionConfig) -> None:
        # Gemini uses per-turn processes; nothing to pre-start
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
            env["GEMINI_API_KEY"] = pcfg.api_key
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
        return shutil.which("gemini") is not None

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
            "gemini",
            "-p", prompt,
            "-o", "stream-json",
        ]
        model = config.get_provider_config(self.name).model or config.model
        if model:
            cmd += ["-m", model]
        cmd += config.permission_flags(self.name)
        cmd += config.get_provider_config(self.name).extra_flags
        return cmd

    def _parse_event(self, obj: dict) -> Event | None:
        etype = obj.get("type", "")

        # Init — session metadata
        if etype == "init":
            self._session_id = obj.get("session_id", self._session_id)
            return Event(type=EventType.SESSION_START, provider=self.name, raw=obj)

        # Message — user/assistant text chunks
        if etype == "message":
            role = obj.get("role", "")
            text = obj.get("content", obj.get("text", ""))
            if role == "user":
                return None  # skip user echo
            return Event(
                type=EventType.TEXT_DELTA,
                provider=self.name,
                text=text,
                raw=obj,
            )

        # Tool use — tool call request
        if etype == "tool_use":
            tool_name = obj.get("name", obj.get("tool", ""))
            return Event(
                type=EventType.TOOL_START,
                provider=self.name,
                tool_name=tool_name,
                tool_category=_TOOL_CATEGORIES.get(tool_name, ToolCategory.OTHER),
                raw=obj,
            )

        # Tool result — output from executed tool
        if etype == "tool_result":
            return Event(
                type=EventType.TOOL_END,
                provider=self.name,
                tool_name=obj.get("name", ""),
                text=obj.get("output", obj.get("content", "")),
                raw=obj,
            )

        # Result — final outcome
        if etype == "result":
            text = obj.get("result", obj.get("content", ""))
            if isinstance(text, dict):
                text = text.get("text", str(text))
            return Event(
                type=EventType.TEXT_COMPLETE,
                provider=self.name,
                text=str(text),
                raw=obj,
            )

        # Error handling
        if etype == "error":
            msg = obj.get("message", obj.get("error", ""))
            if isinstance(msg, dict):
                msg = str(msg)
            msg = str(msg)
            if "429" in msg or "rate_limit" in msg.lower() or "quota" in msg.lower():
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
