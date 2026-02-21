#!/usr/bin/env bash
# AgentSwitch — start with Cursor provider, full-auto permissions
cd "$(dirname "$0")"
exec python3 -m agentswitch --provider cursor --permissions full-auto "$@"
