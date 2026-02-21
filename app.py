"""Simple terminal chat wrapper around Claude Code CLI using bidirectional streaming."""

import argparse
import asyncio
import json
import os
import sys


# ANSI color helpers
def dim(s): return f"\033[2m{s}\033[0m"
def cyan(s): return f"\033[36m{s}\033[0m"
def bold(s): return f"\033[1m{s}\033[0m"
def yellow(s): return f"\033[33m{s}\033[0m"
def red(s): return f"\033[31m{s}\033[0m"
def green(s): return f"\033[32m{s}\033[0m"


def tool_summary(name, inp):
    n = name.lower()
    if n in ("read",): return inp.get("file_path", "")
    if n in ("edit", "write"): return inp.get("file_path", "")
    if n in ("bash",):
        cmd = inp.get("command", "")
        return cmd[:80] + ("..." if len(cmd) > 80 else "")
    if n in ("glob",): return inp.get("pattern", "")
    if n in ("grep",): return inp.get("pattern", "")
    return str(inp)[:80]


session_id = "default"


async def read_stdout(process):
    """Read and display streamed events from claude."""
    global session_id
    in_text = False
    text_shown = False

    while True:
        raw = await process.stdout.readline()
        if not raw:
            break
        line = raw.decode().strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        etype = event.get("type", "")

        # Session init
        if etype == "system":
            sid = event.get("session_id", "")
            if sid:
                session_id = sid

        # Text streaming
        elif etype == "content_block_delta":
            delta = event.get("delta", {})
            if delta.get("type") == "text_delta":
                text = delta.get("text", "")
                if not in_text:
                    print(f"\n{green('Claude:')} ", end="", flush=True)
                    in_text = True
                    text_shown = True
                print(text, end="", flush=True)

        # Content block boundaries
        elif etype == "content_block_start":
            cb = event.get("content_block", {})
            if cb.get("type") == "tool_use":
                if in_text:
                    print()
                    in_text = False
                name = cb.get("name", "?")
                inp = cb.get("input", {})
                print(cyan(f"  > {name}: {tool_summary(name, inp)}"))

        elif etype == "content_block_stop":
            pass

        # Tool results
        elif etype == "tool_result":
            content = event.get("content", "")
            if isinstance(content, list):
                content = "\n".join(
                    b.get("text", "") for b in content if b.get("type") == "text"
                )
            if content:
                preview = str(content)[:120].replace("\n", " ")
                print(dim(f"  <- {preview}"))

        # Assistant message (complete, non-streaming fallback)
        elif etype == "assistant":
            msg = event.get("message", {})
            if isinstance(msg, dict):
                for block in msg.get("content", []):
                    if block.get("type") == "text":
                        if not in_text:
                            print(f"\n{green('Claude:')} ", end="", flush=True)
                            in_text = True
                            text_shown = True
                        print(block["text"], end="", flush=True)

        # Final result
        elif etype == "result":
            if in_text:
                print()
                in_text = False
            # Capture session_id from result
            sid = event.get("session_id", "")
            if sid:
                session_id = sid
            text = event.get("result", "")
            if text and isinstance(text, str) and not text_shown:
                print(f"\n{green('Claude:')} {text}")
            text_shown = False  # reset for next turn
            cost = event.get("total_cost_usd")
            duration = event.get("duration_ms")
            if cost is not None or duration is not None:
                parts = []
                if duration: parts.append(f"{duration}ms")
                if cost: parts.append(f"${cost:.4f}")
                print(dim(f"  [{', '.join(parts)}]"))
            print()  # blank line after response

        # Errors
        elif etype == "error":
            if in_text:
                print()
                in_text = False
            print(red(f"Error: {event.get('error', event)}"))

        # Debug: uncomment to see all events
        # else:
        #     print(dim(f"  [{etype}] {json.dumps(event)[:200]}"))


def parse_args():
    parser = argparse.ArgumentParser(description="Claude Code TUI")
    parser.add_argument(
        "--model", default="haiku",
        help="Model to use (default: haiku)",
    )
    parser.add_argument(
        "--permission-mode", default="bypassPermissions",
        choices=["default", "acceptEdits", "bypassPermissions", "dontAsk", "plan"],
        help="Permission mode (default: bypassPermissions)",
    )
    parser.add_argument(
        "--tools", nargs="*", default=None,
        help='Tools to enable, e.g. "Bash" "Edit" "Read". Omit for all tools.',
    )
    parser.add_argument(
        "--allowed-tools", nargs="*", default=None,
        help='Whitelist specific tools, e.g. "Bash(git:*)" "Edit"',
    )
    parser.add_argument(
        "--disallowed-tools", nargs="*", default=None,
        help='Blacklist specific tools',
    )
    parser.add_argument(
        "--cwd", default=None,
        help="Working directory for claude (default: current directory)",
    )
    return parser.parse_args()


async def main():
    args = parse_args()
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    cmd = [
        "claude",
        "-p",
        "--output-format", "stream-json",
        "--input-format", "stream-json",
        "--include-partial-messages",
        "--verbose",
        "--model", args.model,
        "--permission-mode", args.permission_mode,
    ]
    if args.tools is not None:
        cmd.extend(["--tools", *args.tools])
    if args.allowed_tools is not None:
        cmd.extend(["--allowedTools", *args.allowed_tools])
    if args.disallowed_tools is not None:
        cmd.extend(["--disallowedTools", *args.disallowed_tools])

    cwd = args.cwd or os.getcwd()

    print(bold("Claude Code TUI"))
    print(dim(f"Model: {args.model} | Permissions: {args.permission_mode} | CWD: {cwd}"))
    print(dim("Type your message and press Enter. Ctrl+C to quit.\n"))

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
        cwd=cwd,
    )

    # Start reading stdout in background
    reader_task = asyncio.create_task(read_stdout(process))

    # Also read stderr in background for debugging
    async def read_stderr():
        while True:
            raw = await process.stderr.readline()
            if not raw:
                break
            line = raw.decode().strip()
            if line:
                print(red(f"[stderr] {line}"), flush=True)

    stderr_task = asyncio.create_task(read_stderr())

    # Read user input from stdin in a thread (blocking readline)
    loop = asyncio.get_event_loop()

    try:
        while True:
            # Read input in thread to not block event loop
            try:
                user_input = await loop.run_in_executor(
                    None, lambda: input("> ")
                )
            except EOFError:
                break

            user_input = user_input.strip()
            if not user_input:
                continue

            print(f"{bold('You:')} {user_input}")

            if user_input.lower() in ("/quit", "/exit"):
                break

            # Send message to claude via stdin as JSON
            msg = json.dumps({
                "type": "user",
                "message": {
                    "role": "user",
                    "content": user_input,
                },
                "session_id": session_id,
                "parent_tool_use_id": None,
            }) + "\n"
            process.stdin.write(msg.encode())
            await process.stdin.drain()

    except KeyboardInterrupt:
        print(dim("\nGoodbye!"))
    finally:
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=3)
        except asyncio.TimeoutError:
            process.kill()
        reader_task.cancel()
        stderr_task.cancel()


if __name__ == "__main__":
    asyncio.run(main())
