"""Configuration types for AgentSwitch."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# Permissions normalization: unified name → per-provider CLI flags
PERMISSIONS_MAP: dict[str, dict[str, list[str]]] = {
    "default": {
        "claude": ["--permission-mode", "default"],
        "codex": [],
        "cursor": [],
        "gemini": [],
    },
    "readonly": {
        "claude": ["--permission-mode", "plan"],
        "codex": ["-s", "read-only"],
        "cursor": ["--mode", "plan"],
        "gemini": ["--approval-mode", "plan"],
    },
    "full-auto": {
        "claude": ["--dangerously-skip-permissions"],
        "codex": ["--full-auto"],
        "cursor": [],
        "gemini": ["-y"],
    },
}


@dataclass
class ProviderConfig:
    model: str = ""
    api_key: str = ""
    extra_flags: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    timeout: float = 300.0


@dataclass
class SessionConfig:
    workspace: str = "."
    model: str = ""
    permissions: str = "default"
    allowed_tools: list[str] = field(default_factory=list)
    disallowed_tools: list[str] = field(default_factory=list)
    fallback_order: list[str] = field(default_factory=list)
    auto_failover: bool = True
    provider_configs: dict[str, ProviderConfig] = field(default_factory=dict)

    def get_provider_config(self, provider: str) -> ProviderConfig:
        return self.provider_configs.get(provider, ProviderConfig())

    def permission_flags(self, provider: str) -> list[str]:
        perm = PERMISSIONS_MAP.get(self.permissions, PERMISSIONS_MAP["default"])
        return perm.get(provider, [])

    def update(self, **kwargs: Any) -> None:
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
