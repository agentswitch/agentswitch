"""Provider registry for AgentSwitch."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import Provider

from .claude import ClaudeProvider
from .codex import CodexProvider
from .cursor import CursorProvider

PROVIDER_CLASSES: dict[str, type[Provider]] = {
    "claude": ClaudeProvider,
    "codex": CodexProvider,
    "cursor": CursorProvider,
}

__all__ = [
    "PROVIDER_CLASSES",
    "ClaudeProvider",
    "CodexProvider",
    "CursorProvider",
]
