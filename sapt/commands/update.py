"""
sapt.commands.update
Handler for 'sapt update'.
"""

from sapt.security.audit import AuditLogger


def handle_update(args, config, display):
    """Handle 'sapt update'."""
    from sapt.execution.executor import Executor

    display.banner_mini()
    executor = Executor(display=display)
    audit = AuditLogger()

    try:
        result = executor.update()
        audit.log(
            action="update",
            success=result.success,
            command=result.command,
        )
        return 0 if result.success else 1
    except Exception as e:
        audit.log(
            action="update",
            success=False,
            command="",
            details=f"CRASH: {str(e)}",
        )
        raise
