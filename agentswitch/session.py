"""Session — owns transcript, hot-swap logic, and auto-failover."""

from __future__ import annotations

from typing import Any, AsyncIterator

from .config import SessionConfig
from .errors import AllProvidersExhausted, ProviderNotFound
from .providers.base import Provider
from .types import Event, EventType, Message


class Session:
    """A conversation session that can span multiple providers.

    The session owns the transcript and handles hot-swapping between
    providers while preserving conversation context.
    """

    def __init__(
        self,
        providers: dict[str, Provider],
        config: SessionConfig,
    ) -> None:
        self._providers = providers
        self._config = config
        self._transcript: list[Message] = []
        self._active_provider: str = ""

    @property
    def transcript(self) -> list[Message]:
        return list(self._transcript)

    @property
    def active_provider(self) -> str:
        return self._active_provider

    def config(self, **kwargs: Any) -> None:
        """Update session configuration on the fly."""
        self._config.update(**kwargs)

    async def send(
        self,
        prompt: str,
        provider: str | None = None,
        model: str | None = None,
    ) -> AsyncIterator[Event]:
        """Send a message and stream back events.

        If provider changes from the current one, the old provider is
        stopped and the transcript is replayed to the new one.
        """
        # Apply per-call overrides
        if model:
            self._config.model = model

        target = provider or self._active_provider or self._pick_default()
        if target not in self._providers:
            raise ProviderNotFound(target)

        # Add user message to transcript
        user_msg = Message(role="user", content=prompt)
        self._transcript.append(user_msg)

        # Try the target provider, with failover
        tried: list[str] = []
        providers_to_try = self._failover_order(target)

        for pname in providers_to_try:
            if pname not in self._providers:
                continue
            tried.append(pname)

            # Hot-swap: stop old provider if switching
            if self._active_provider and self._active_provider != pname:
                old = self._providers.get(self._active_provider)
                if old:
                    await old.stop()

            self._active_provider = pname
            prov = self._providers[pname]

            # Build messages for the provider
            messages = self._transcript

            assistant_text = ""
            rate_limited = False

            async for event in prov.send(messages, self._config):
                if event.type == EventType.TEXT_DELTA:
                    assistant_text += event.text
                elif event.type == EventType.TEXT_COMPLETE:
                    if event.text and not assistant_text:
                        assistant_text = event.text
                elif event.type == EventType.RATE_LIMIT:
                    rate_limited = True
                    yield event
                    break

                yield event

            if rate_limited and self._config.auto_failover:
                continue  # try next provider

            # Record assistant response in transcript
            if assistant_text:
                self._transcript.append(
                    Message(
                        role="assistant",
                        content=assistant_text,
                        provider=pname,
                        model=self._config.model,
                    )
                )
            return

        raise AllProvidersExhausted(tried)

    async def close(self) -> None:
        """Stop all providers and clean up."""
        for prov in self._providers.values():
            await prov.stop()

    def _pick_default(self) -> str:
        """Pick the first available provider."""
        if self._config.fallback_order:
            for name in self._config.fallback_order:
                if name in self._providers:
                    return name
        return next(iter(self._providers))

    def _failover_order(self, primary: str) -> list[str]:
        """Build an ordered list of providers to try, starting with primary."""
        order = [primary]
        if self._config.auto_failover:
            fallback = self._config.fallback_order or list(self._providers.keys())
            for name in fallback:
                if name not in order:
                    order.append(name)
        return order
