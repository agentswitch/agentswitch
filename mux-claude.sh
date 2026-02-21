#!/usr/bin/env bash
# AgentSwitch — start with Claude provider, full-auto permissions
cd "$(dirname "$0")"
exec python3 -m agentswitch --provider claude --permissions full-auto "$@"
