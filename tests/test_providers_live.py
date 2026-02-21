"""Live integration tests — sends a real prompt to each provider and verifies output.

Run:  python3 tests/test_providers_live.py
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from agentswitch.router import AgentRouter
from agentswitch.types import EventType

PROMPT = "Say only the word 'pong'. Do not say anything else."
TIMEOUT = 60


async def _test_provider(
    router: AgentRouter,
    name: str,
) -> str:
    """Send a prompt to *name*, return 'PASS' or raise on failure."""
    session = router.session(
        workspace=os.getcwd(),
        permissions="full-auto",
        auto_failover=False,
    )
    events: list = []
    text_chunks: list[str] = []
    got_complete = False

    try:
        async for event in session.send(PROMPT, provider=name):
            events.append(event)
            print(f"    [{event.type.value:15s}] text={event.text!r:.60}", flush=True)
            if event.type == EventType.TEXT_DELTA:
                text_chunks.append(event.text)
            elif event.type == EventType.TEXT_COMPLETE:
                got_complete = True
                if event.text and not text_chunks:
                    text_chunks.append(event.text)
    finally:
        await session.close()

    full_text = "".join(text_chunks).strip().lower()
    print(f"    => response: {full_text!r}", flush=True)

    assert events, f"No events received from {name}"
    assert got_complete, f"Never got TEXT_COMPLETE from {name}"
    assert "pong" in full_text, f"Expected 'pong' in response, got: {full_text!r}"
    return "PASS"


async def main() -> None:
    print("=== AgentSwitch Live Provider Tests ===\n", flush=True)

    router = AgentRouter()
    discovered = await router.discover()
    print(f"Discovered: {list(discovered.keys())}\n", flush=True)

    results: dict[str, str] = {}
    for name in ["claude", "codex", "cursor"]:
        print(f"  [{name}]", flush=True)
        if name not in discovered:
            print("    SKIP: not installed\n", flush=True)
            results[name] = "SKIP"
            continue
        try:
            results[name] = await asyncio.wait_for(
                _test_provider(router, name), timeout=TIMEOUT
            )
        except asyncio.TimeoutError:
            results[name] = f"TIMEOUT ({TIMEOUT}s)"
        except Exception as exc:
            results[name] = f"FAIL: {type(exc).__name__}: {exc}"
        print(f"    => {results[name]}\n", flush=True)

    print("=== Summary ===", flush=True)
    for n, s in results.items():
        print(f"  {n}: {s}", flush=True)

    installed = [n for n in results if n in discovered]
    failed = [n for n in installed if not results[n].startswith("PASS")]
    if failed:
        print(f"\nFAILED: {failed}", flush=True)
        sys.exit(1)
    print("\nAll available providers passed!", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
