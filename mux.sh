#!/usr/bin/env bash
# AgentSwitch — default launcher (auto-discover providers, drop into REPL)
cd "$(dirname "$0")"
exec python3 -m agentswitch "$@"
