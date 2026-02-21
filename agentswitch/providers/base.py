"""Abstract base for provider adapters."""

from __future__ import annotations

import abc
from typing import AsyncIterator

from ..config import SessionConfig
from ..types import Event, Message


class Provider(abc.ABC):
    """Protocol that every provider adapter must implement."""

    name: str

    @abc.abstractmethod
    async def start(self, config: SessionConfig) -> None:
        """Initialize the provider (spawn long-lived process, etc.)."""

    @abc.abstractmethod
    async def send(
        self,
        messages: list[Message],
        config: SessionConfig,
    ) -> AsyncIterator[Event]:
        """Send messages and stream back unified events."""

    @abc.abstractmethod
    async def stop(self) -> None:
        """Tear down any running processes."""

    @abc.abstractmethod
    async def is_available(self) -> bool:
        """Check if this provider's CLI is installed and reachable."""
