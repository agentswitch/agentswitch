#!/usr/bin/env bash
# AgentSwitch — start with Gemini provider, full-auto permissions
cd "$(dirname "$0")"
exec python3 -m agentswitch --provider gemini --permissions full-auto "$@"
