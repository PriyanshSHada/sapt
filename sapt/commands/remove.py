"""
sapt.commands.remove
Handler for 'sapt remove <package>'.
"""

from sapt.security.audit import AuditLogger


def handle_remove(args, config, display):
    """Handle 'sapt remove <package>'."""
    from sapt.execution.executor import Executor

    display.banner_mini()
    executor = Executor(display=display)
    audit = AuditLogger()

    try:
        result = executor.remove(
            package=args.package,
            purge=args.clean,
            auto_yes=args.yes,
        )
        audit.log(
            action="remove" if not args.clean else "purge",
            package=args.package,
            success=result.success,
            command=result.command,
        )
        return 0 if result.success else 1
    except Exception as e:
        audit.log(
            action="remove" if not args.clean else "purge",
            package=args.package,
            success=False,
            command="",
            details=f"CRASH: {str(e)}",
        )
        raise
