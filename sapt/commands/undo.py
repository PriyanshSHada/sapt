"""
sapt.commands.undo
Handler for 'sapt undo'.
"""

from sapt.security.audit import AuditLogger


def handle_undo(args, config, display):
    """Reverse the latest successful, reversible package action."""
    from sapt.ai.resolver import PackageResolution
    from sapt.execution.executor import Executor

    display.banner_mini()
    audit = AuditLogger()
    reversible = {"install", "remove", "purge"}
    target = next(
        (
            entry
            for entry in reversed(audit.get_all())
            if entry.get("success")
            and entry.get("action") in reversible
            and entry.get("package")
        ),
        None,
    )
    if target is None:
        display.info(
            "No successful install, remove, or purge action is available to undo."
        )
        return 0

    package = target["package"]
    action = target["action"]
    executor = Executor(display=display)
    if action == "install":
        display.info(f"Undoing install of [sapt.package]{package}[/] by removing it.")
        result = executor.remove(
            package,
            dry_run=args.dry_run,
            auto_yes=args.yes,
        )
        inverse = "remove"
    else:
        display.warning(
            f"Undoing {action} reinstalls the currently available APT version; "
            "the removed version may no longer be available."
        )
        resolution = PackageResolution(
            package=package,
            source="apt",
            confidence=1.0,
            trust_tier=1,
            notes="Reinstalled while undoing a previous SmartAPT action.",
        )
        result = executor.install(
            resolution,
            dry_run=args.dry_run,
            auto_yes=args.yes,
        )
        inverse = "install"

    if not args.dry_run:
        audit.log(
            action="undo",
            package=package,
            source="apt",
            source_tier=1,
            success=result.success,
            command=result.command,
            details=f"Reversed {action} entry {target.get('id', 'unknown')} via {inverse}.",
        )
    return 0 if result.success else 1
