"""Unified event model for AgentSwitch."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


class EventType(enum.Enum):
    TEXT_DELTA = "text_delta"
    TEXT_COMPLETE = "text_complete"
    THINKING = "thinking"
    TOOL_START = "tool_start"
    TOOL_OUTPUT = "tool_output"
    TOOL_END = "tool_end"
    ERROR = "error"
    RATE_LIMIT = "rate_limit"
    INPUT_REQUIRED = "input_required"
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    RAW = "raw"


class ToolCategory(enum.Enum):
    BASH = "bash"
    FILE_EDIT = "file_edit"
    FILE_READ = "file_read"
    SEARCH = "search"
    WEB = "web"
    OTHER = "other"


@dataclass
class Event:
    type: EventType
    provider: str = ""
    text: str = ""
    tool_name: str = ""
    tool_category: ToolCategory | None = None
    error_message: str = ""
    retry_after: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    output: str = ""
    category: ToolCategory = ToolCategory.OTHER


@dataclass
class Message:
    role: str  # "user" or "assistant"
    content: str
    provider: str = ""
    model: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
