"""AgentSwitch — Unified Coding Agent SDK for Python.

A "LiteLLM for coding agents" that wraps Claude Code, Codex CLI,
and Cursor Agent behind a unified streaming interface with mid-conversation
hot-swapping, dynamic config, and auto-failover.
"""

from .config import ProviderConfig, SessionConfig
from .models import ModelInfo, get_model, models_for_provider, resolve_model
from .discovery import ProviderInfo
from .errors import (
    AgentSwitchError,
    AllProvidersExhausted,
    ProviderAuthError,
    ProviderNotFound,
    RateLimitError,
)
from .router import AgentRouter
from .session import Session
from .types import Event, EventType, Message, ToolCall, ToolCategory

__all__ = [
    "AgentSwitchError",
    "AgentRouter",
    "AllProvidersExhausted",
    "Event",
    "EventType",
    "Message",
    "ModelInfo",
    "ProviderAuthError",
    "ProviderConfig",
    "ProviderInfo",
    "ProviderNotFound",
    "RateLimitError",
    "Session",
    "SessionConfig",
    "ToolCall",
    "ToolCategory",
]
