"""Detect installed CLI agents, their versions, and auth status."""

from __future__ import annotations

import asyncio
import os
import pathlib
import shutil
from dataclasses import dataclass, field


@dataclass
class ProviderInfo:
    name: str
    cli_path: str = ""
    version: str = ""
    authenticated: bool = False
    capabilities: list[str] = field(default_factory=list)


# CLI binary name, version flag, and auth check command for each provider
_PROVIDER_SPECS: list[tuple[str, str, list[str], list[str]]] = [
    ("claude", "claude", ["claude", "--version"], ["claude", "auth", "status"]),
    ("codex", "codex", ["codex", "--version"], []),
    ("cursor", "cursor-agent", ["cursor-agent", "--version"], []),
]


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


async def _check_one(
    name: str,
    binary: str,
    version_cmd: list[str],
    auth_cmd: list[str],
) -> ProviderInfo | None:
    search_path = _extended_path()
    cli_path = shutil.which(binary, path=search_path)
    if not cli_path:
        return None

    info = ProviderInfo(name=name, cli_path=cli_path)

    # Get version
    try:
        proc = await asyncio.create_subprocess_exec(
            *version_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10.0)
        info.version = stdout.decode("utf-8", errors="replace").strip()
    except (asyncio.TimeoutError, OSError):
        pass

    # Check auth
    if auth_cmd:
        try:
            proc = await asyncio.create_subprocess_exec(
                *auth_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=10.0)
            info.authenticated = proc.returncode == 0
        except (asyncio.TimeoutError, OSError):
            info.authenticated = False
    else:
        # No auth check available — assume authenticated if installed
        info.authenticated = True

    return info


async def discover_providers() -> dict[str, ProviderInfo]:
    """Detect all installed CLI agents concurrently.

    Returns a dict mapping provider name to ProviderInfo for each
    provider whose CLI binary is found on PATH.
    """
    tasks = [
        _check_one(name, binary, ver_cmd, auth_cmd)
        for name, binary, ver_cmd, auth_cmd in _PROVIDER_SPECS
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    providers: dict[str, ProviderInfo] = {}
    for result in results:
        if isinstance(result, ProviderInfo) and result is not None:
            providers[result.name] = result
    return providers
