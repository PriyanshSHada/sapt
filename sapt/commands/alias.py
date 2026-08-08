"""
sapt.commands.alias
Handler for 'sapt alias'.
"""

from sapt.commands._helpers import emit_json


def handle_alias(args, config, display):
    """Create, list, or remove validated local package aliases."""
    from sapt.config.aliases import AliasError, AliasManager

    manager = AliasManager()
    try:
        if args.remove:
            if not args.name:
                display.error("Provide an alias name to remove.")
                return 1
            if manager.remove(args.name):
                display.success(f"Removed alias: {args.name}")
                return 0
            display.warning(f"Alias not found: {args.name}")
            return 1

        aliases = manager.list()
        if args.list or not args.name:
            if args.json:
                emit_json({"aliases": aliases})
            elif aliases:
                for name, package in aliases.items():
                    display.info(
                        f"[sapt.package]{name}[/] → [sapt.package]{package}[/]"
                    )
            else:
                display.info("No aliases configured.")
            return 0

        if not args.package:
            target = manager.resolve(args.name)
            if args.json:
                emit_json({"alias": args.name, "package": target})
            elif target:
                display.info(
                    f"[sapt.package]{args.name}[/] → [sapt.package]{target}[/]"
                )
                return 0
            else:
                display.warning(f"Alias not found: {args.name}")
                return 1

        manager.set(args.name, args.package)
        display.success(f"Alias set: {args.name} → {args.package}")
        return 0
    except AliasError as error:
        display.error(str(error))
        return 1
