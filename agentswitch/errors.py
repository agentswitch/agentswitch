"""Exception types for AgentSwitch."""

from __future__ import annotations


class AgentSwitchError(Exception):
    """Base exception for all AgentSwitch errors."""


class ProviderNotFound(AgentSwitchError):
    """Requested provider is not installed or not discovered."""

    def __init__(self, provider: str) -> None:
        self.provider = provider
        super().__init__(f"Provider not found: {provider}")


class ProviderAuthError(AgentSwitchError):
    """Provider CLI is installed but not authenticated."""

    def __init__(self, provider: str, message: str = "") -> None:
        self.provider = provider
        msg = f"Provider not authenticated: {provider}"
        if message:
            msg += f" ({message})"
        super().__init__(msg)


class RateLimitError(AgentSwitchError):
    """Provider returned a rate limit / overloaded response."""

    def __init__(self, provider: str, retry_after: float | None = None) -> None:
        self.provider = provider
        self.retry_after = retry_after
        msg = f"Rate limited by {provider}"
        if retry_after is not None:
            msg += f" (retry after {retry_after}s)"
        super().__init__(msg)


class AllProvidersExhausted(AgentSwitchError):
    """Every provider in the fallback order failed or was rate-limited."""

    def __init__(self, providers: list[str]) -> None:
        self.providers = providers
        super().__init__(
            f"All providers exhausted: {', '.join(providers)}"
        )
