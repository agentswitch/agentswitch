"""Entry point: python -m agentchat"""

import asyncio
import os
import sys

# Ensure the project root is importable (for running without pip install)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agentchat.app import main  # noqa: E402

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
