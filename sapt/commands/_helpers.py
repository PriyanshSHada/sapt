"""
sapt.commands._helpers
Shared utilities for command handlers.
"""

import sys
import json


def emit_json(data):
    """Write a single JSON document for a non-interactive report command."""
    sys.stdout.write(json.dumps(data, ensure_ascii=False, default=str) + "\n")
