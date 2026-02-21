#!/usr/bin/env bash
# AgentSwitch — start in readonly mode (safe exploration)
cd "$(dirname "$0")"
exec python3 -m agentswitch --permissions readonly "$@"
