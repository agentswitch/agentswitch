"""Interactive REPL for AgentSwitch — explore and hot-swap AI coding agents."""

from __future__ import annotations

import asyncio
import os
import sys
from typing import TYPE_CHECKING

from .errors import AllProvidersExhausted, ProviderNotFound, RateLimitError
from .router import AgentRouter
from .types import EventType

if TYPE_CHECKING:
    from argparse import Namespace

    from .session import Session

# ── ANSI helpers ──────────────────────────────────────────────────────────────

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"

PROVIDER_COLORS: dict[str, str] = {
    "claude": MAGENTA,
    "codex": GREEN,
    "cursor": CYAN,
}


def _c(color: str, text: str) -> str:
    return f"{color}{text}{RESET}"


# ── Banner ────────────────────────────────────────────────────────────────────

BANNER = rf"""
{BOLD}    _                _   ___        _ _      _
   /_\  __ _ ___ _ _| |_/ __|_ __ _(_) |_ __| |_
  / _ \/ _` / -_) ' \  _\__ \ V  V / |  _/ _| ' \\
 /_/ \_\__, \___|_||_\__|___/\_/\_/|_|\__\__|_||_|
       |___/{RESET}
  {DIM}Interactive REPL — hot-swap AI coding agents{RESET}
"""

HELP_TEXT = f"""\
{BOLD}Commands:{RESET}
  /provider <name>    (/p)     Switch provider (claude, codex, cursor)
  /model <name>       (/m)     Change model
  /permissions <lvl>  (/perm)  Set permissions (default, readonly, full-auto)
  /workspace <path>   (/ws)    Change workspace directory
  /failover <p1,p2>            Set failover order
  /auto-failover on|off        Toggle auto-failover
  /transcript         (/t)     Show conversation transcript
  /providers                   List discovered providers
  /config                      Show current session config
  /clear                       Clear transcript, start fresh
  /help               (/h)     Show this help
  /quit               (/q)     Exit
"""


# ── Async readline input ─────────────────────────────────────────────────────

async def _async_input(prompt: str) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: input(prompt))


# ── Event printer ─────────────────────────────────────────────────────────────

def _print_event(event, provider_color: str) -> None:  # noqa: ANN001
    if event.type is EventType.TEXT_DELTA:
        sys.stdout.write(f"{provider_color}{event.text}{RESET}")
        sys.stdout.flush()
    elif event.type is EventType.TEXT_COMPLETE:
        # Ensure we end on a new line after streaming
        sys.stdout.write("\n")
        sys.stdout.flush()
    elif event.type is EventType.THINKING:
        sys.stdout.write(f"{DIM}{event.text}{RESET}")
        sys.stdout.flush()
    elif event.type is EventType.TOOL_START:
        print(f"\n{YELLOW}[tool: {event.tool_name}]{RESET}")
    elif event.type is EventType.TOOL_OUTPUT:
        if event.text:
            for line in event.text.splitlines()[:10]:
                print(f"  {DIM}{line}{RESET}")
    elif event.type is EventType.TOOL_END:
        print(f"{YELLOW}[/tool]{RESET}")
    elif event.type is EventType.ERROR:
        print(f"\n{RED}error: {event.error_message}{RESET}")
    elif event.type is EventType.RATE_LIMIT:
        retry = f" (retry after {event.retry_after}s)" if event.retry_after else ""
        print(f"\n{YELLOW}rate-limited by {event.provider}{retry}{RESET}")


# ── Command handlers ─────────────────────────────────────────────────────────

class ReplState:
    """Mutable state bag for the REPL loop."""

    def __init__(self, router: AgentRouter, session: Session, args: Namespace) -> None:
        self.router = router
        self.session = session
        self.provider: str = args.provider or ""
        self.model: str = args.model or ""
        self.permissions: str = args.permissions
        self.workspace: str = args.workspace
        self.auto_failover: bool = not args.no_failover
        self.fallback_order: list[str] = (
            [p.strip() for p in args.fallback.split(",") if p.strip()]
            if args.fallback
            else []
        )

    # Convenience ---------------------------------------------------------

    @property
    def prompt(self) -> str:
        p = self.provider or "auto"
        m = self.model or "default"
        perm = self.permissions
        color = PROVIDER_COLORS.get(p, "")
        return f"{color}[{p}|{m}|{perm}]>{RESET} "


def _handle_command(line: str, state: ReplState) -> bool:
    """Handle a slash-command. Returns True to continue the loop, False to quit."""
    parts = line.split(None, 1)
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    # ── provider ──
    if cmd in ("/provider", "/p"):
        if not arg:
            print(f"{RED}Usage: /provider <name>{RESET}")
            return True
        if arg not in state.router.providers:
            print(f"{RED}Unknown provider '{arg}'. Use /providers to list.{RESET}")
            return True
        state.provider = arg
        color = PROVIDER_COLORS.get(arg, "")
        print(f"Switched to {color}{arg}{RESET}")

    # ── model ──
    elif cmd in ("/model", "/m"):
        if not arg:
            print(f"{RED}Usage: /model <name>{RESET}")
            return True
        state.model = arg
        print(f"Model set to {BOLD}{arg}{RESET}")

    # ── permissions ──
    elif cmd in ("/permissions", "/perm"):
        valid = ("default", "readonly", "full-auto")
        if arg not in valid:
            print(f"{RED}Usage: /permissions {{{', '.join(valid)}}}{RESET}")
            return True
        state.permissions = arg
        state.session.config(permissions=arg)
        print(f"Permissions set to {BOLD}{arg}{RESET}")

    # ── workspace ──
    elif cmd in ("/workspace", "/ws"):
        path = os.path.expanduser(arg) if arg else os.getcwd()
        if not os.path.isdir(path):
            print(f"{RED}Not a directory: {path}{RESET}")
            return True
        state.workspace = os.path.abspath(path)
        state.session.config(workspace=state.workspace)
        print(f"Workspace set to {BOLD}{state.workspace}{RESET}")

    # ── failover ──
    elif cmd == "/failover":
        if not arg:
            print(f"{RED}Usage: /failover claude,codex,cursor{RESET}")
            return True
        order = [p.strip() for p in arg.split(",") if p.strip()]
        state.fallback_order = order
        state.session.config(fallback_order=order)
        print(f"Failover order: {BOLD}{', '.join(order)}{RESET}")

    elif cmd == "/auto-failover":
        if arg.lower() in ("on", "true", "1"):
            state.auto_failover = True
            state.session.config(auto_failover=True)
            print("Auto-failover {BOLD}enabled{RESET}")
        elif arg.lower() in ("off", "false", "0"):
            state.auto_failover = False
            state.session.config(auto_failover=False)
            print(f"Auto-failover {BOLD}disabled{RESET}")
        else:
            print(f"{RED}Usage: /auto-failover on|off{RESET}")

    # ── transcript ──
    elif cmd in ("/transcript", "/t"):
        transcript = state.session.transcript
        if not transcript:
            print(f"{DIM}(empty transcript){RESET}")
        else:
            for msg in transcript:
                role_color = CYAN if msg.role == "user" else PROVIDER_COLORS.get(msg.provider, MAGENTA)
                label = msg.role
                if msg.provider:
                    label += f" ({msg.provider})"
                print(f"{role_color}{BOLD}{label}:{RESET} {msg.content[:200]}")
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        print(f"  {YELLOW}[tool: {tc.name}]{RESET}")

    # ── providers ──
    elif cmd == "/providers":
        providers = state.router.providers
        if not providers:
            print(f"{DIM}No providers discovered.{RESET}")
        else:
            for name, info in providers.items():
                color = PROVIDER_COLORS.get(name, "")
                auth = f"{GREEN}authenticated" if info.authenticated else f"{RED}not authenticated"
                active = " *" if name == state.provider else ""
                print(f"  {color}{BOLD}{name}{RESET} v{info.version} [{auth}{RESET}]{active}")

    # ── config ──
    elif cmd == "/config":
        print(f"  provider:      {BOLD}{state.provider or 'auto'}{RESET}")
        print(f"  model:         {BOLD}{state.model or 'default'}{RESET}")
        print(f"  permissions:   {BOLD}{state.permissions}{RESET}")
        print(f"  workspace:     {BOLD}{state.workspace}{RESET}")
        print(f"  failover:      {BOLD}{', '.join(state.fallback_order) or 'auto'}{RESET}")
        print(f"  auto-failover: {BOLD}{'on' if state.auto_failover else 'off'}{RESET}")

    # ── clear ──
    elif cmd == "/clear":
        # Recreate session to clear transcript
        state.session = state.router.session(
            workspace=state.workspace,
            model=state.model,
            permissions=state.permissions,
            fallback_order=state.fallback_order or None,
            auto_failover=state.auto_failover,
        )
        print(f"{DIM}Transcript cleared, new session started.{RESET}")

    # ── help ──
    elif cmd in ("/help", "/h"):
        print(HELP_TEXT)

    # ── quit ──
    elif cmd in ("/quit", "/q"):
        return False

    else:
        print(f"{RED}Unknown command: {cmd}  (try /help){RESET}")

    return True


# ── Main loop ─────────────────────────────────────────────────────────────────

async def run(args: Namespace) -> None:
    """Entry point for the interactive REPL."""
    print(BANNER)

    router = AgentRouter()
    print(f"{DIM}Discovering providers...{RESET}")
    discovered = await router.discover()

    if not discovered:
        print(f"{RED}No providers found. Install claude, codex, or cursor CLI first.{RESET}")
        return

    for name, info in discovered.items():
        color = PROVIDER_COLORS.get(name, "")
        auth = f"{GREEN}ok" if info.authenticated else f"{RED}no auth"
        print(f"  {color}{BOLD}{name}{RESET} v{info.version} [{auth}{RESET}]")
    print()

    # Pick initial provider if not specified
    if args.provider and args.provider not in discovered:
        print(f"{RED}Provider '{args.provider}' not found, using first available.{RESET}")
        args.provider = ""
    if not args.provider:
        args.provider = next(iter(discovered))

    session = router.session(
        workspace=args.workspace,
        model=args.model or "",
        permissions=args.permissions,
        fallback_order=(
            [p.strip() for p in args.fallback.split(",") if p.strip()]
            if args.fallback
            else None
        ),
        auto_failover=not args.no_failover,
    )

    state = ReplState(router, session, args)

    color = PROVIDER_COLORS.get(state.provider, "")
    print(f"Ready. Using {color}{BOLD}{state.provider}{RESET}. Type /help for commands.\n")

    try:
        while True:
            try:
                line = await _async_input(state.prompt)
            except EOFError:
                break

            line = line.strip()
            if not line:
                continue

            if line.startswith("/"):
                if not _handle_command(line, state):
                    break
                continue

            # Send message to provider
            provider_color = PROVIDER_COLORS.get(state.provider, "")
            try:
                async for event in session.send(
                    line,
                    provider=state.provider or None,
                    model=state.model or None,
                ):
                    _print_event(event, provider_color)
            except ProviderNotFound as exc:
                print(f"\n{RED}Provider not found: {exc.provider}{RESET}")
                print(f"{DIM}Use /providers to see available providers.{RESET}")
            except RateLimitError as exc:
                retry = f" Retry after {exc.retry_after}s." if exc.retry_after else ""
                print(f"\n{YELLOW}Rate limited by {exc.provider}.{retry}{RESET}")
                print(f"{DIM}Try /provider <other> to switch, or wait and retry.{RESET}")
            except AllProvidersExhausted as exc:
                print(f"\n{RED}All providers exhausted: {', '.join(exc.providers)}{RESET}")
                print(f"{DIM}Wait for rate limits to reset or check provider status.{RESET}")
            except KeyboardInterrupt:
                print(f"\n{DIM}(interrupted){RESET}")

            print()  # blank line after response

    except KeyboardInterrupt:
        pass
    finally:
        print(f"\n{DIM}Goodbye.{RESET}")
        await session.close()


if __name__ == "__main__":
    from .__main__ import main
    main()
