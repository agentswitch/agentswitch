"""Shared subprocess helpers for provider adapters."""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
from typing import AsyncIterator


def _extended_path() -> str:
    """Build a PATH that includes common user-local bin directories."""
    path = os.environ.get("PATH", "")
    home = pathlib.Path.home()
    extra = [
        str(home / ".local" / "bin"),
        str(home / ".cargo" / "bin"),
        str(home / "bin"),
        "/usr/local/bin",
    ]
    parts = path.split(os.pathsep)
    for d in extra:
        if d not in parts:
            parts.append(d)
    return os.pathsep.join(parts)


async def spawn(
    cmd: list[str],
    env: dict[str, str] | None = None,
    cwd: str | None = None,
    stdin_pipe: bool = True,
) -> asyncio.subprocess.Process:
    """Spawn a subprocess with optional env overlay and working directory."""
    merged_env = dict(os.environ)
    merged_env["PATH"] = _extended_path()
    # Remove vars that block nested CLI sessions
    merged_env.pop("CLAUDECODE", None)
    merged_env.pop("CLAUDE_CODE_ENTRYPOINT", None)
    if env:
        merged_env.update(env)
    return await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE if stdin_pipe else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=merged_env,
        cwd=cwd,
    )


async def read_jsonl(
    proc: asyncio.subprocess.Process,
    timeout: float = 300.0,
) -> AsyncIterator[dict]:
    """Read newline-delimited JSON objects from a process's stdout.

    Yields parsed dicts. Silently skips blank or non-JSON lines.
    Stops when stdout is closed or the process exits.
    """
    assert proc.stdout is not None
    try:
        while True:
            try:
                line_bytes = await asyncio.wait_for(
                    proc.stdout.readline(), timeout=timeout
                )
            except asyncio.TimeoutError:
                break
            if not line_bytes:
                break
            line = line_bytes.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue
    except asyncio.CancelledError:
        raise


async def write_json(proc: asyncio.subprocess.Process, obj: dict) -> None:
    """Write a JSON object followed by newline to the process's stdin."""
    assert proc.stdin is not None
    data = json.dumps(obj) + "\n"
    proc.stdin.write(data.encode("utf-8"))
    await proc.stdin.drain()


async def terminate(proc: asyncio.subprocess.Process) -> None:
    """Gracefully terminate a subprocess."""
    if proc.returncode is not None:
        return
    try:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
    except ProcessLookupError:
        pass
