#!/usr/bin/env bash
# AgentSwitch — start with Codex provider, full-auto permissions
cd "$(dirname "$0")"
exec python3 -m agentswitch --provider codex --permissions full-auto "$@"
