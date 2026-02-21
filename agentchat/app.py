"""AgentChat — setup wizard, raw-terminal chat loop, and display engine."""

from __future__ import annotations

import asyncio
import fcntl
import os
import re
import sys
import termios
import tty

from agentswitch.discovery import discover_providers
from agentswitch.models import models_for_provider, resolve_model

from .agent import AGENT_COLORS, AgentConfig, AgentState, ChatAgent
from .bus import ChatMessage, MessageBus

# ── ANSI helpers ─────────────────────────────────────────────────────────────

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
WHITE = "\033[37m"
GRAY = "\033[90m"


def _clear():
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()


def _divider(ch: str = "\u2500", width: int = 60):
    print(f"  {DIM}{ch * width}{RESET}")


# ── Raw terminal ─────────────────────────────────────────────────────────────

class RawTerminal:
    """Character-at-a-time terminal for async chat I/O."""

    def __init__(self):
        self.fd = sys.stdin.fileno()
        self._old_attr = None
        self._old_flags = None
        self.buf = ""
        self.prompt = f"  {BOLD}You{RESET} > "
        self.prompt_len = 8  # "  You > "

    def __enter__(self):
        self._old_attr = termios.tcgetattr(self.fd)
        self._old_flags = fcntl.fcntl(self.fd, fcntl.F_GETFL)
        tty.setcbreak(self.fd)
        fcntl.fcntl(self.fd, fcntl.F_SETFL, self._old_flags | os.O_NONBLOCK)
        return self

    def __exit__(self, *_):
        if self._old_attr:
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self._old_attr)
        if self._old_flags is not None:
            fcntl.fcntl(self.fd, fcntl.F_SETFL, self._old_flags)

    def read_chars(self) -> str:
        try:
            return os.read(self.fd, 1024).decode("utf-8", errors="replace")
        except (BlockingIOError, OSError):
            return ""

    def write(self, text: str):
        sys.stdout.write(text)
        sys.stdout.flush()

    def clear_line(self):
        self.write("\r\033[K")

    def redraw(self):
        self.write(f"\r\033[K{self.prompt}{self.buf}")

    def println(self, text: str):
        """Print *text* above the current input line."""
        self.clear_line()
        self.write(f"{text}\n")
        self.redraw()

    def process(self, raw: str) -> str | None:
        """Feed raw chars into the buffer.  Returns a line on Enter, else None."""
        i = 0
        while i < len(raw):
            ch = raw[i]
            if ch in ("\r", "\n"):
                line = self.buf
                self.buf = ""
                return line
            elif ch in ("\x7f", "\x08"):          # backspace
                if self.buf:
                    self.buf = self.buf[:-1]
            elif ch == "\x03":                     # Ctrl-C
                raise KeyboardInterrupt
            elif ch == "\x04":                     # Ctrl-D
                raise EOFError
            elif ch == "\x1b":                     # escape seq — skip
                i += 1
                while i < len(raw) and raw[i] not in "ABCDHFPQRSTfsu~":
                    i += 1
            elif ch >= " ":                        # printable
                self.buf += ch
            i += 1
        self.redraw()
        return None


# ── display formatters ───────────────────────────────────────────────────────

def _fmt_agent(name: str, color: str, text: str) -> str:
    # Indent continuation lines
    lines = text.split("\n")
    first = f"  {color}{BOLD}{name}{RESET}: {lines[0]}"
    rest = [f"    {l}" for l in lines[1:]]
    return "\n".join([first] + rest)


def _fmt_human(text: str) -> str:
    return f"  {BOLD}You{RESET}: {text}"


def _fmt_system(text: str) -> str:
    return f"  {DIM}[system] {text}{RESET}"


def _fmt_status(name: str, color: str, detail: str) -> str:
    return f"  {color}{DIM}  \u21b3 {name}: {detail}{RESET}"


def _fmt_task_assign(assignee: str, task: str) -> str:
    return f"  {YELLOW}{BOLD}>> Task{RESET} {DIM}\u2192 {assignee}: {task}{RESET}"


def _color_for(name: str, agents: list[ChatAgent]) -> str:
    for a in agents:
        if a.config.name == name:
            return a.config.color
    return ""


def _render_bus_msg(msg: ChatMessage, agents: list[ChatAgent]) -> str | None:
    """Render a bus message for display.  Returns None to skip."""
    if msg.sender == "You":
        return None  # human messages are echoed on input, not from bus

    if msg.kind == "chat":
        color = _color_for(msg.sender, agents)
        text = msg.body.get("text", "")
        if not text:
            return None
        return _fmt_agent(msg.sender, color, text)

    if msg.kind == "status":
        color = _color_for(msg.sender, agents)
        state = msg.body.get("state", "")
        detail = msg.body.get("detail", "")
        if state == "thinking":
            return f"  {color}{DIM}  {msg.sender} is thinking \u2026{RESET}"
        if detail:
            return _fmt_status(msg.sender, color, detail)
        return None

    if msg.kind == "task":
        assignee = msg.body.get("assignee", "?")
        task = msg.body.get("task", "")
        return _fmt_task_assign(assignee, task)

    if msg.kind == "system":
        return _fmt_system(msg.body.get("text", ""))

    return None


# ── setup wizard (normal terminal mode) ──────────────────────────────────────

def _banner():
    _clear()
    w = 56
    print()
    print(f"  {BOLD}{CYAN}\u256d{'\u2500' * w}\u256e{RESET}")
    print(f"  {BOLD}{CYAN}\u2502{RESET}{BOLD}{'AgentChat':^{w}}{RESET}{BOLD}{CYAN}\u2502{RESET}")
    print(f"  {BOLD}{CYAN}\u2502{RESET}{DIM}{'Multi-Agent Group Chat for Coding':^{w}}{RESET}{BOLD}{CYAN}\u2502{RESET}")
    print(f"  {BOLD}{CYAN}\u2570{'\u2500' * w}\u256f{RESET}")
    print()


async def _ask_workspace() -> str:
    cwd = os.getcwd()
    print(f"  {BOLD}Project folder{RESET} {DIM}(Enter for {cwd}){RESET}")
    raw = await asyncio.to_thread(input, "  > ")
    path = raw.strip() or cwd
    path = os.path.abspath(os.path.expanduser(path))
    if not os.path.isdir(path):
        print(f"  {RED}Not a directory: {path}{RESET}")
        return await _ask_workspace()

    entries = sorted(os.listdir(path))[:12]
    if entries:
        preview = ", ".join(entries[:8])
        if len(entries) > 8:
            preview += f", \u2026 (+{len(entries) - 8})"
        print(f"  {DIM}Contents: {preview}{RESET}")
    print()
    return path


async def _setup_agents(providers: dict) -> list[AgentConfig]:
    prov_names = list(providers.keys())
    agents: list[AgentConfig] = []
    color_i = 0

    while True:
        print(f"  {BOLD}Add agent #{len(agents) + 1}{RESET}")

        # name
        default = f"Agent-{len(agents) + 1}"
        raw = await asyncio.to_thread(input, f"    Name {DIM}({default}){RESET}: ")
        name = raw.strip() or default
        if any(a.name.lower() == name.lower() for a in agents):
            print(f"    {RED}Name already used.{RESET}")
            continue

        # provider
        print(f"    Providers: {', '.join(prov_names)}")
        raw = await asyncio.to_thread(
            input, f"    Provider {DIM}({prov_names[0]}){RESET}: ",
        )
        prov = raw.strip().lower() or prov_names[0]
        if prov not in providers:
            print(f"    {RED}Unknown. Pick from: {', '.join(prov_names)}{RESET}")
            continue

        # model
        avail = models_for_provider(prov)
        default_model = avail[0].id if avail else ""
        if avail:
            ids = [m.id for m in avail]
            print(f"    Models: {', '.join(ids[:6])}")
            if len(ids) > 6:
                print(f"            {', '.join(ids[6:])}")
        raw = await asyncio.to_thread(
            input, f"    Model {DIM}({default_model}){RESET}: ",
        )
        model = raw.strip() or default_model
        model_id = resolve_model(model, prov)

        color = AGENT_COLORS[color_i % len(AGENT_COLORS)]
        color_i += 1

        agents.append(AgentConfig(
            name=name, provider=prov, model=model,
            model_id=model_id, color=color,
        ))
        print(f"    {color}{BOLD}\u2713 {name}{RESET} {DIM}({prov}/{model}){RESET}")
        print()

        raw = await asyncio.to_thread(
            input, f"  {BOLD}Add another agent?{RESET} {DIM}(y/N){RESET}: ",
        )
        if raw.strip().lower() not in ("y", "yes"):
            break
        print()

    return agents


# ── command handling ─────────────────────────────────────────────────────────

def _parse_mentions(text: str, agents: list[ChatAgent]) -> list[ChatAgent]:
    lower = text.lower()
    return [a for a in agents if f"@{a.config.name.lower()}" in lower]


_HELP_TEXT = f"""
  {BOLD}Commands:{RESET}
    {BOLD}/assign @name task{RESET}  Assign a coding task to an agent
    {BOLD}/status{RESET}             Show agent states
    {BOLD}/history{RESET}            Show recent messages
    {BOLD}/clear{RESET}              Clear the screen
    {BOLD}/help{RESET}               Show this help
    {BOLD}/quit{RESET}               Exit
"""


async def _handle_command(
    text: str,
    term: RawTerminal,
    bus: MessageBus,
    agents: list[ChatAgent],
    bg_tasks: set[asyncio.Task],
) -> bool:
    """Handle a slash command. Returns True to quit."""
    parts = text.split(None, 1)
    cmd = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    if cmd in ("/quit", "/q", "/exit"):
        return True

    if cmd in ("/help", "/h"):
        for line in _HELP_TEXT.strip().split("\n"):
            term.println(line)
        return False

    if cmd == "/status":
        term.println("")
        for a in agents:
            sc = GREEN if a.state == AgentState.IDLE else YELLOW
            task_info = f" \u2014 {a.current_task}" if a.current_task else ""
            term.println(
                f"    {a.config.color}{BOLD}{a.config.name}{RESET} "
                f"{sc}{a.state.value}{RESET}"
                f"{DIM}{task_info}{RESET}"
            )
        term.println("")
        return False

    if cmd == "/history":
        term.println("")
        for msg in bus.get_recent(20):
            rendered = _render_bus_msg(msg, agents)
            if rendered:
                term.println(rendered)
            elif msg.sender == "You" and msg.kind == "chat":
                term.println(_fmt_human(msg.body.get("text", "")))
        term.println("")
        return False

    if cmd == "/clear":
        _clear()
        term.redraw()
        return False

    if cmd == "/assign":
        m = re.match(r"@(\S+)\s+(.+)", args)
        if not m:
            term.println(f"  {RED}Usage: /assign @agent-name task description{RESET}")
            return False
        target_name, task_desc = m.group(1), m.group(2)
        target = next(
            (a for a in agents if a.config.name.lower() == target_name.lower()),
            None,
        )
        if target is None:
            names = ", ".join(a.config.name for a in agents)
            term.println(f"  {RED}Unknown agent. Available: {names}{RESET}")
            return False
        if target.state != AgentState.IDLE:
            term.println(
                f"  {YELLOW}{target.config.name} is busy "
                f"({target.state.value}). Try again later.{RESET}"
            )
            return False

        bus.post("You", "task", {"assignee": target.config.name, "task": task_desc})
        chat_history = bus.get_recent(50)
        team = [a.config for a in agents]

        async def _run_task():
            result, tools = await target.work_on_task(task_desc, chat_history, team)
            if result:
                bus.post(target.config.name, "chat", {"text": result})
            if tools:
                bus.post(target.config.name, "status", {
                    "state": "idle",
                    "detail": f"done \u2014 used {', '.join(tools)}",
                })

        bg_tasks.add(asyncio.create_task(_run_task()))
        return False

    term.println(f"  {RED}Unknown command: {cmd} \u2014 type /help{RESET}")
    return False


# ── chat loop (raw terminal) ────────────────────────────────────────────────

async def _chat_loop(bus: MessageBus, agents: list[ChatAgent], workspace: str):
    team = [a.config for a in agents]
    last_id = 0
    bg_tasks: set[asyncio.Task] = set()

    # header
    print()
    _divider("\u2501", 60)
    agent_chips = "  ".join(
        f"{a.config.color}{BOLD}{a.config.name}{RESET}"
        f"{DIM}({a.config.provider}/{a.config.model}){RESET}"
        for a in agents
    )
    print(f"  {BOLD}AgentChat{RESET} {DIM}\u2502{RESET} {workspace}")
    print(f"  {agent_chips}")
    _divider("\u2501", 60)
    print()
    print(f"  {DIM}Chat with your agents. @name to direct a message.{RESET}")
    print(f"  {DIM}/assign @name task \u2014 give work  |  /help \u2014 commands  |  /quit{RESET}")
    _divider()
    print()

    bus.post("system", "system", {"text": "Chat started."})

    with RawTerminal() as term:
        # advance past existing bus messages
        for msg in bus.poll_since(0):
            last_id = msg.id

        term.redraw()

        while True:
            # ── read available keystrokes ────────────────────────────────
            chars = term.read_chars()
            if chars:
                try:
                    line = term.process(chars)
                except (KeyboardInterrupt, EOFError):
                    term.println(f"\n  {DIM}Goodbye!{RESET}")
                    break

                if line is not None:
                    text = line.strip()
                    if not text:
                        term.redraw()
                        await asyncio.sleep(0.02)
                        continue

                    # echo the human message
                    term.clear_line()
                    term.write(f"{_fmt_human(text)}\n")

                    if text.startswith("/"):
                        should_quit = await _handle_command(
                            text, term, bus, agents, bg_tasks,
                        )
                        if should_quit:
                            break
                        term.redraw()
                        await asyncio.sleep(0.02)
                        continue

                    # regular chat message
                    bus.post("You", "chat", {"text": text})
                    chat_history = bus.get_recent(50)

                    mentioned = _parse_mentions(text, agents)
                    responders = mentioned or [
                        a for a in agents if a.state == AgentState.IDLE
                    ]

                    for agent in responders:
                        async def _reply(a=agent):
                            resp, tools = await a.respond(chat_history, team)
                            if resp:
                                bus.post(a.config.name, "chat", {"text": resp})
                            if tools:
                                bus.post(a.config.name, "status", {
                                    "state": "idle",
                                    "detail": f"used {', '.join(tools)}",
                                })

                        bg_tasks.add(asyncio.create_task(_reply()))

                    term.redraw()

            # ── display new bus messages ─────────────────────────────────
            new = bus.poll_since(last_id)
            for msg in new:
                last_id = msg.id
                rendered = _render_bus_msg(msg, agents)
                if rendered:
                    term.println(rendered)

            # ── clean up finished tasks ──────────────────────────────────
            done = {t for t in bg_tasks if t.done()}
            for t in done:
                exc = t.exception()
                if exc:
                    term.println(f"  {RED}[Error] {exc}{RESET}")
            bg_tasks -= done

            await asyncio.sleep(0.04)  # ~25 Hz


# ── entry point ──────────────────────────────────────────────────────────────

async def main():
    _banner()

    # discover providers
    print(f"  {DIM}Detecting providers \u2026{RESET}")
    providers = await discover_providers()

    if not providers:
        print(f"  {RED}No providers found.{RESET}")
        print(f"  {DIM}Install one of: claude, codex, gemini, cursor-agent{RESET}")
        return

    for name, info in providers.items():
        ver = (info.version.split("\n")[0][:40]) if info.version else "?"
        auth = f"{GREEN}auth{RESET}" if info.authenticated else f"{YELLOW}ready{RESET}"
        print(f"    {GREEN}\u2713{RESET} {BOLD}{name}{RESET} {DIM}({ver}){RESET} \u2014 {auth}")
    print()

    # workspace
    workspace = await _ask_workspace()

    # agents
    agent_configs = await _setup_agents(providers)
    if not agent_configs:
        print(f"  {RED}No agents configured.{RESET}")
        return

    # initialize
    print()
    print(f"  {DIM}Starting agents \u2026{RESET}")
    bus = MessageBus()
    agents: list[ChatAgent] = []

    for cfg in agent_configs:
        agent = ChatAgent(cfg, bus, workspace)
        try:
            await agent.start()
            agents.append(agent)
            print(f"    {cfg.color}{BOLD}\u2713 {cfg.name}{RESET} ready")
        except Exception as exc:
            print(f"    {RED}\u2717 {cfg.name}: {exc}{RESET}")

    if not agents:
        print(f"  {RED}No agents started.{RESET}")
        return

    # run chat
    try:
        await _chat_loop(bus, agents, workspace)
    finally:
        print(f"\n  {DIM}Shutting down \u2026{RESET}")
        for agent in agents:
            await agent.stop()
        print(f"  {DIM}Done.{RESET}\n")
