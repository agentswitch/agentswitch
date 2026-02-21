"""ChatAgent — wraps an agentswitch provider with group-chat awareness."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

import os

from agentswitch.config import SessionConfig
from agentswitch.models import resolve_model
from agentswitch.providers import PROVIDER_CLASSES
from agentswitch.types import EventType, Message

SCRATCHPAD_DIR = ".agentchat"

if TYPE_CHECKING:
    from .bus import ChatMessage, MessageBus


# ── constants ────────────────────────────────────────────────────────────────

class AgentState(str, Enum):
    IDLE = "idle"
    THINKING = "thinking"
    WORKING = "working"


AGENT_COLORS = [
    "\033[36m",   # cyan
    "\033[35m",   # magenta
    "\033[33m",   # yellow
    "\033[32m",   # green
    "\033[34m",   # blue
    "\033[91m",   # bright red
    "\033[96m",   # bright cyan
    "\033[95m",   # bright magenta
]


# ── config ───────────────────────────────────────────────────────────────────

@dataclass
class AgentConfig:
    name: str
    provider: str
    model: str
    model_id: str = ""   # provider-specific CLI model arg
    color: str = ""


# ── agent ────────────────────────────────────────────────────────────────────

VERBOSITY_PROMPTS = {
    "brief": (
        "CHAT STYLE: Be terse. 1-2 sentences max in chat. "
        "Think of this like Slack — short punchy messages, not essays.\n"
        "If you did work, just say what you did in one line "
        '(e.g. "Created server.js with Express + 3 routes"). '
        "Put details, code snippets, and explanations in your scratchpad log.\n"
        "The human will ask you to elaborate if they want more.\n"
    ),
    "normal": (
        "CHAT STYLE: Keep responses to a short paragraph (3-5 sentences). "
        "Summarize what you did or what you think. "
        "Put long code listings and detailed specs in the scratchpad.\n"
    ),
    "verbose": (
        "CHAT STYLE: Be thorough. Include details, code snippets, "
        "and full explanations directly in your chat response.\n"
    ),
}


class ChatAgent:
    """A single agent in the group chat, backed by an agentswitch provider."""

    def __init__(
        self,
        config: AgentConfig,
        bus: MessageBus,
        workspace: str,
    ):
        self.config = config
        self.bus = bus
        self.workspace = workspace
        self.state = AgentState.IDLE
        self.current_task: str | None = None
        self.provider = None
        self.verbosity = "brief"
        self._session_config = SessionConfig(
            workspace=workspace,
            model=config.model_id or resolve_model(config.model, config.provider),
            permissions="full-auto",
        )

    async def start(self) -> None:
        provider_cls = PROVIDER_CLASSES.get(self.config.provider)
        if provider_cls is None:
            raise ValueError(f"Unknown provider: {self.config.provider}")
        self.provider = provider_cls()
        await self.provider.start(self._session_config)
        # ensure shared scratchpad directory
        pad = os.path.join(self.workspace, SCRATCHPAD_DIR)
        os.makedirs(pad, exist_ok=True)

    async def stop(self) -> None:
        if self.provider:
            await self.provider.stop()

    # ── prompt construction ──────────────────────────────────────────────

    def _build_context(
        self,
        chat_history: list[ChatMessage],
        team: list[AgentConfig],
    ) -> str:
        team_desc = ", ".join(
            f"{a.name} ({a.provider}/{a.model})"
            for a in team
        )

        lines: list[str] = []
        for msg in chat_history[-30:]:
            if msg.kind == "chat":
                lines.append(f"[{msg.sender}]: {msg.body.get('text', '')}")
            elif msg.kind == "status":
                detail = msg.body.get("detail", "")
                if detail:
                    lines.append(f"  * {msg.sender}: {detail}")
            elif msg.kind == "task":
                assignee = msg.body.get("assignee", "?")
                task = msg.body.get("task", "")
                lines.append(f"  >> Task assigned to {assignee}: {task}")
            elif msg.kind == "system":
                lines.append(f"  [system] {msg.body.get('text', '')}")

        chat_text = "\n".join(lines) if lines else "(no messages yet)"

        verbosity_inst = VERBOSITY_PROMPTS.get(
            self.verbosity, VERBOSITY_PROMPTS["brief"],
        )

        return (
            f"You are {self.config.name}, a coding agent in a group chat.\n"
            f"Provider: {self.config.provider} | Model: {self.config.model}\n"
            f"Project workspace: {self.workspace}\n"
            f"Team: {team_desc}, and the human (You)\n"
            f"\n"
            f"Recent conversation:\n"
            f"{chat_text}\n"
            f"\n"
            f"{verbosity_inst}\n"
            f"Respond as {self.config.name}. Rules:\n"
            f"- When asked to BUILD, FIX, or CREATE something — DO IT NOW.\n"
            f"  Use your tools: read files, write code, run commands. Act, don't discuss.\n"
            f"- Don't ask for permission — start working. Create files, write code, run tests.\n"
            f"- The human can jump in anytime. Follow their direction when they do.\n"
            f"- If another agent already handled something, don't redo it — build on it.\n"
            f"\n"
            f"Team coordination — use {SCRATCHPAD_DIR}/ in the workspace:\n"
            f"- BEFORE starting work: read {SCRATCHPAD_DIR}/plan.md to see the team plan.\n"
            f"  If it doesn't exist yet, create it with the high-level plan and your role.\n"
            f"- WHILE working: update {SCRATCHPAD_DIR}/{self.config.name.lower()}-log.md\n"
            f"  with what you've done, what files you created/changed, and what's left.\n"
            f"- BEFORE building on others' work: read their log\n"
            f"  (e.g. {SCRATCHPAD_DIR}/<teammate>-log.md) to see what they've built.\n"
        )

    # ── respond ──────────────────────────────────────────────────────────

    async def respond(
        self,
        chat_history: list[ChatMessage],
        team: list[AgentConfig],
    ) -> tuple[str, list[str]]:
        """Generate a response. Returns (text, tools_used)."""
        self.state = AgentState.THINKING
        self.bus.post(self.config.name, "status", {"state": "thinking"})

        context = self._build_context(chat_history, team)
        messages = [Message(role="user", content=context)]

        full_text = ""
        tools_used: list[str] = []

        try:
            async for event in self.provider.send(messages, self._session_config):
                if event.type == EventType.TEXT_DELTA:
                    full_text += event.text
                elif event.type == EventType.TEXT_COMPLETE:
                    if event.text and not full_text:
                        full_text = event.text
                elif event.type == EventType.TOOL_START:
                    self.state = AgentState.WORKING
                    tools_used.append(event.tool_name)
                    self.bus.post(self.config.name, "status", {
                        "state": "working",
                        "detail": f"using {event.tool_name}",
                    })
                elif event.type == EventType.ERROR:
                    full_text += f"\n[Error: {event.error_message}]"
                elif event.type == EventType.RATE_LIMIT:
                    full_text += "\n[Rate limited — try again later]"
                    break
        except Exception as exc:
            full_text = f"[Error: {exc}]"

        self.state = AgentState.IDLE
        self.bus.post(self.config.name, "status", {"state": "idle"})
        return full_text.strip(), tools_used

    async def work_on_task(
        self,
        task_desc: str,
        chat_history: list[ChatMessage],
        team: list[AgentConfig],
    ) -> tuple[str, list[str]]:
        """Execute a coding task. Returns (summary, tools_used)."""
        self.state = AgentState.WORKING
        self.current_task = task_desc
        self.bus.post(self.config.name, "status", {
            "state": "working",
            "detail": f"starting task: {task_desc[:60]}",
        })

        context = self._build_context(chat_history, team)
        prompt = (
            f"{context}\n\n"
            f"You have been assigned the following task:\n"
            f"  {task_desc}\n\n"
            f"Work on it now. Use your tools to read, edit, and test code.\n"
            f"When finished, summarize what you did."
        )
        messages = [Message(role="user", content=prompt)]

        full_text = ""
        tools_used: list[str] = []

        try:
            async for event in self.provider.send(messages, self._session_config):
                if event.type == EventType.TEXT_DELTA:
                    full_text += event.text
                elif event.type == EventType.TEXT_COMPLETE:
                    if event.text and not full_text:
                        full_text = event.text
                elif event.type == EventType.TOOL_START:
                    tools_used.append(event.tool_name)
                    self.bus.post(self.config.name, "status", {
                        "state": "working",
                        "detail": f"using {event.tool_name}",
                    })
                elif event.type == EventType.ERROR:
                    full_text += f"\n[Error: {event.error_message}]"
                elif event.type == EventType.RATE_LIMIT:
                    full_text += "\n[Rate limited — try again later]"
                    break
        except Exception as exc:
            full_text = f"[Error: {exc}]"

        self.state = AgentState.IDLE
        self.current_task = None
        self.bus.post(self.config.name, "status", {"state": "idle"})
        return full_text.strip(), tools_used
