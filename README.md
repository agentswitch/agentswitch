# AgentSwitch

**One SDK for every AI coding agent.**

Claude Code, Codex CLI, Cursor Agent — each has its own CLI, its own streaming format, its own quirks. If you want to use more than one, you're writing three integrations. If one hits a rate limit, you're stuck.

AgentSwitch gives you a single async Python interface across all of them. Send a prompt, get a unified event stream. Switch providers mid-conversation. Auto-failover when one is down. Zero dependencies beyond stdlib.

```bash
pip install git+https://github.com/agentswitch/agentswitch.git
```

Or build from source:

```bash
git clone https://github.com/agentswitch/agentswitch.git
cd agentswitch
pip install -e .
```

> Requires Python 3.11+ and at least one CLI installed: `claude`, `codex`, or `cursor-agent`

## Quick start

```python
import asyncio
from agentswitch import AgentRouter, EventType

async def main():
    router = AgentRouter()
    await router.discover()

    session = router.session(permissions="full-auto")

    async for event in session.send("Write a hello world script"):
        if event.type == EventType.TEXT_DELTA:
            print(event.text, end="", flush=True)

    await session.close()

asyncio.run(main())
```

## Pick a provider

```python
session = router.session(permissions="full-auto")

# Use Claude
async for event in session.send("Explain this codebase", provider="claude"):
    ...

# Switch to Codex mid-conversation — context carries over
async for event in session.send("Now refactor the auth module", provider="codex"):
    ...
```

## Auto-failover

If Claude is rate-limited, AgentSwitch automatically tries the next provider:

```python
session = router.session(
    fallback_order=["claude", "codex", "cursor"],
    auto_failover=True,
)
```

## Handle events

Every provider emits the same event types:

```python
async for event in session.send(prompt, provider="claude"):
    match event.type:
        case EventType.TEXT_DELTA:    print(event.text, end="")
        case EventType.TOOL_START:   print(f"\n[{event.tool_name}]")
        case EventType.TOOL_END:     print(f"[/{event.tool_name}]")
        case EventType.THINKING:     pass  # internal reasoning
        case EventType.ERROR:        print(f"Error: {event.error_message}")
        case EventType.TEXT_COMPLETE: break
```

## Error handling

```python
from agentswitch import ProviderNotFound, RateLimitError, AllProvidersExhausted

try:
    async for event in session.send("hello"):
        ...
except RateLimitError as e:
    print(f"Rate limited by {e.provider}, retry after {e.retry_after}s")
except AllProvidersExhausted:
    print("Every provider is down")
except ProviderNotFound:
    print("Provider not installed")
```

## Interactive REPL

Don't want to write code? Just run it:

```bash
python3 -m agentswitch
```

```
    _                _   ___        _ _      _
   /_\  __ _ ___ _ _| |_/ __|_ __ _(_) |_ __| |_
  / _ \/ _` / -_) ' \  _\__ \ V  V / |  _/ _| ' \
 /_/ \_\__, \___|_||_\__|___/\_/\_/|_|\__\__|_||_|
       |___/

Discovering providers...
  claude v2.1.49 [ok]
  codex  v0.104.0 [ok]
  cursor v2026.02 [ok]

Ready. Using claude. Type /help for commands.

[claude|default|default]> Explain this repo
```

**Slash commands** — change anything without leaving the conversation:

| Command | Short | What it does |
|---|---|---|
| `/provider claude` | `/p` | Switch provider (hot-swap) |
| `/model sonnet-4.6` | `/m` | Change model |
| `/permissions full-auto` | `/perm` | Set permissions |
| `/workspace ~/project` | `/ws` | Change working directory |
| `/providers` | | List discovered providers |
| `/config` | | Show current settings |
| `/transcript` | `/t` | Show conversation history |
| `/clear` | | Start fresh session |

**Preset launchers:**

```bash
./mux.sh                  # auto-discover, drop into REPL
./mux-claude.sh            # claude + full-auto
./mux-codex.sh             # codex + full-auto
./mux-cursor.sh            # cursor + full-auto
./mux-readonly.sh          # safe read-only mode
```

## Supported providers

| Provider | CLI binary | Status |
|---|---|---|
| Claude Code | `claude` | Streaming, tools, thinking |
| Codex CLI | `codex` | Streaming, tools, reasoning |
| Cursor Agent | `cursor-agent` | Streaming, tools |

## SDK roadmap

What's working today vs what's next:

| Feature | Status |
|---|---|
| Unified streaming events | Done |
| Provider discovery | Done |
| Hot-swap mid-conversation | Done |
| Auto-failover on rate limit | Done |
| Interactive REPL | Done |
| Permission levels (default/readonly/full-auto) | Done |
| Tool use events (start/end/output) | Done |
| `pip install` from source/git | Done |
| Custom tool injection (MCP passthrough) | Not yet |
| Bidirectional streaming (long-lived sessions) | Not yet |
| Provider plugins (bring your own adapter) | Not yet |
| Cost tracking across providers | Not yet |
| Structured output / JSON mode | Not yet |
| Parallel multi-provider queries | Not yet |

## Architecture

```
agentswitch/
├── router.py          # AgentRouter — discover + session factory
├── session.py         # Session — transcript, hot-swap, failover
├── types.py           # Event, EventType, Message, ToolCall
├── config.py          # SessionConfig, ProviderConfig, permissions
├── discovery.py       # CLI detection + version/auth checks
├── errors.py          # AgentSwitchError hierarchy
├── _subprocess.py     # Async process spawn + JSONL reader
├── interactive.py     # Terminal REPL
├── __main__.py        # python3 -m agentswitch entry point
└── providers/
    ├── base.py        # Provider abstract base class
    ├── claude.py      # Claude Code adapter
    ├── codex.py       # Codex CLI adapter
    └── cursor.py      # Cursor Agent adapter
```

Zero external dependencies. Python 3.11+ stdlib only.

## License

MIT
