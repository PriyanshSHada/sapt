"""
sapt.commands
Command handler registry — maps CLI command names to handler functions.

Each handler lives in its own module for testability and maintainability.
"""

from sapt.commands.install import handle_install
from sapt.commands.remove import handle_remove
from sapt.commands.update import handle_update
from sapt.commands.upgrade import handle_upgrade
from sapt.commands.search import handle_search
from sapt.commands.explain import handle_explain
from sapt.commands.learn import handle_learn
from sapt.commands.ask import handle_ask
from sapt.commands.doctor import handle_doctor
from sapt.commands.history import handle_history
from sapt.commands.why import handle_why
from sapt.commands.diff import handle_diff
from sapt.commands.undo import handle_undo
from sapt.commands.agent import handle_agent
from sapt.commands.cache_cmd import handle_cache
from sapt.commands.audit import handle_audit
from sapt.commands.completion import handle_completion
from sapt.commands.alias import handle_alias
from sapt.commands.config_cmd import handle_config
from sapt.commands.list_cmd import handle_list
from sapt.commands.version import handle_version

# ── Command Handler Map ──────────────────────────────────────────
COMMAND_HANDLERS = {
    "install": handle_install,
    "remove": handle_remove,
    "update": handle_update,
    "upgrade": handle_upgrade,
    "search": handle_search,
    "explain": handle_explain,
    "learn": handle_learn,
    "ask": handle_ask,
    "doctor": handle_doctor,
    "why": handle_why,
    "diff": handle_diff,
    "undo": handle_undo,
    "agent": handle_agent,
    "cache": handle_cache,
    "audit": handle_audit,
    "completion": handle_completion,
    "alias": handle_alias,
    "list": handle_list,
    "version": handle_version,
}

__all__ = ["COMMAND_HANDLERS", "handle_config", "handle_history"]
