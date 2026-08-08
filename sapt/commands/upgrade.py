"""
sapt.commands.upgrade
Handler for 'sapt upgrade'.
"""

from sapt.security.audit import AuditLogger


def handle_upgrade(args, config, display):
    """Handle 'sapt upgrade'."""
    from sapt.execution.executor import Executor

    display.banner_mini()
    executor = Executor(display=display)
    audit = AuditLogger()

    try:
        result = executor.upgrade(auto_yes=args.yes)
        audit.log(
            action="upgrade",
            success=result.success,
            command=result.command,
        )
        return 0 if result.success else 1
    except Exception as e:
        audit.log(
            action="upgrade",
            success=False,
            command="",
            details=f"CRASH: {str(e)}",
        )
        raise
