"""Module entry point: python3 -m agentswitch launches the interactive REPL."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="agentswitch",
        description="AgentSwitch — interactive REPL for hot-swapping AI coding agents",
    )
    parser.add_argument(
        "-p", "--provider",
        default="",
        help="Initial provider (claude, codex, cursor)",
    )
    parser.add_argument(
        "-m", "--model",
        default="",
        help="Initial model name",
    )
    parser.add_argument(
        "--permissions", "--perm",
        default="default",
        choices=("default", "readonly", "full-auto"),
        help="Permission level (default: default)",
    )
    parser.add_argument(
        "-w", "--workspace",
        default=os.getcwd(),
        help="Workspace directory (default: cwd)",
    )
    parser.add_argument(
        "--fallback",
        default="",
        help="Comma-separated fallback provider order",
    )
    parser.add_argument(
        "--no-failover",
        action="store_true",
        help="Disable auto-failover on rate limits",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)

    # Lazy import so --help is fast
    from .interactive import run

    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
