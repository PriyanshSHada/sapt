"""
sapt.commands.diff
Handler for 'sapt diff'.
"""

from sapt.commands._helpers import emit_json
from sapt.ui.themes import ICONS


def handle_diff(args, config, display):
    """Handle 'sapt diff' from SmartAPT's append-only audit history."""
    from rich import box
    from rich.table import Table
    from sapt.security.audit import AuditLogger

    if not args.json:
        display.banner_mini()
    entries = AuditLogger().get_history(args.count)
    changes = [
        entry
        for entry in entries
        if entry.get("action") in {"install", "remove", "purge", "upgrade"}
    ]
    if args.json:
        emit_json({"changes": list(reversed(changes))})
        return 0
    if not changes:
        display.info("No package changes recorded in the selected history.")
        return 0

    symbols = {"install": "+", "remove": "-", "purge": "-", "upgrade": "↑"}
    table = Table(
        title=f"{ICONS['chart']} Recorded Package Changes",
        box=box.ROUNDED,
        border_style="#7C3AED",
    )
    table.add_column("When", style="dim")
    table.add_column("Change", style="bold")
    table.add_column("Package", style="bold cyan")
    table.add_column("Version")
    table.add_column("Source")
    table.add_column("Status")
    for entry in reversed(changes):
        action = entry.get("action", "")
        table.add_row(
            entry.get("timestamp", "")[:19],
            f"{symbols.get(action, '?')} {action}",
            entry.get("package", "system"),
            entry.get("version", "") or "—",
            entry.get("source", "apt"),
            "✓" if entry.get("success") else "✗",
        )
    display.console.print(table)
    return 0
