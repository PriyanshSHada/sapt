"""
sapt.commands.history
Handler for 'sapt history'.
"""

from sapt.commands._helpers import emit_json


def handle_history(args, display):
    """Handle 'sapt history'."""
    from sapt.security.audit import AuditLogger

    display.banner_mini()
    audit = AuditLogger()

    if args.verify:
        with display.spinner("Verifying audit log integrity..."):
            valid, message = audit.verify_chain()
        if args.json:
            emit_json({"valid": valid, "message": message})
        elif valid:
            display.success(message)
        else:
            display.error(message)
        return 0 if valid else 1

    entries = audit.get_history(args.count)
    if args.json:
        emit_json({"entries": entries, "total_entries": audit.entry_count()})
        return 0
    if not entries:
        display.info("No history yet. Start by installing something!")
        return 0

    display.show_history(entries)
    display.muted(f"  {audit.entry_count()} total entries in audit log.")
    display.console.print()
    return 0
