"""AgentRouter — entry point and session factory."""

from __future__ import annotations

from .config import SessionConfig, ProviderConfig
from .discovery import ProviderInfo, discover_providers
from .errors import ProviderNotFound
from .providers import PROVIDER_CLASSES
from .providers.base import Provider
from .session import Session


class AgentRouter:
    """Main entry point for AgentSwitch.

    Discovers installed CLI agents and creates sessions that can
    hot-swap between them mid-conversation.
    """

    def __init__(self) -> None:
        self._discovered: dict[str, ProviderInfo] = {}
        self._providers: dict[str, Provider] = {}

    @property
    def providers(self) -> dict[str, ProviderInfo]:
        """Return discovered provider info."""
        return dict(self._discovered)

    async def discover(self) -> dict[str, ProviderInfo]:
        """Detect installed CLI agents and their capabilities.

        Returns a dict of provider name → ProviderInfo for each
        CLI that was found on PATH.
        """
        self._discovered = await discover_providers()
        self._providers = {}
        for name, info in self._discovered.items():
            cls = PROVIDER_CLASSES.get(name)
            if cls is not None:
                self._providers[name] = cls()
        return self._discovered

    def session(
        self,
        workspace: str = ".",
        model: str = "",
        permissions: str = "default",
        fallback_order: list[str] | None = None,
        auto_failover: bool = True,
        **kwargs,
    ) -> Session:
        """Create a new session with the discovered providers.

        Args:
            workspace: Working directory for the agents.
            model: Default model to use across providers.
            permissions: Permission level ("default", "readonly", "full-auto").
            fallback_order: Ordered list of provider names for failover.
            auto_failover: Whether to auto-switch on rate limit.

        Returns:
            A Session instance ready for send() calls.

        Raises:
            ProviderNotFound: If no providers have been discovered.
        """
        if not self._providers:
            raise ProviderNotFound(
                "No providers discovered. Call await router.discover() first."
            )

        config = SessionConfig(
            workspace=workspace,
            model=model,
            permissions=permissions,
            fallback_order=fallback_order or list(self._providers.keys()),
            auto_failover=auto_failover,
        )
        # Apply any extra kwargs as provider configs or session config fields
        for key, value in kwargs.items():
            if isinstance(value, ProviderConfig) and key in self._providers:
                config.provider_configs[key] = value
            elif hasattr(config, key):
                setattr(config, key, value)

        return Session(providers=dict(self._providers), config=config)
