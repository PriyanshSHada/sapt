"""
sapt.commands.install
Handler for 'sapt install <package>'.
"""

from sapt.security.audit import AuditLogger


def handle_install(args, config, display):
    """Handle 'sapt install <package>'."""
    from sapt.ai.resolver import PackageResolution, PackageResolver
    from sapt.execution.executor import Executor
    from sapt.ui import prompts

    display.banner_mini()
    resolver = None if args.source and args.source != "apt" else PackageResolver(config)
    executor = Executor(display=display)
    audit = AuditLogger()

    if args.version and args.source and args.source != "apt":
        display.error("--version is only supported for APT installs.")
        return 1

    packages = args.package  # Can be multiple
    from sapt.config.aliases import AliasManager

    aliases = AliasManager()

    all_succeeded = True
    for pkg_name in packages:
        alias_target = aliases.resolve(pkg_name)
        if alias_target:
            display.info(
                f"Alias [sapt.package]{pkg_name}[/] → [sapt.package]{alias_target}[/]"
            )
            pkg_name = alias_target
        if args.source and args.source != "apt":
            resolution = PackageResolution(
                package=pkg_name,
                source=args.source,
                confidence=1.0,
                trust_tier=PackageResolver._source_to_tier(args.source),
                notes=f"Using explicit --source {args.source}.",
            )
        else:
            with display.spinner(f"Resolving {pkg_name}..."):
                resolution = resolver.resolve(pkg_name, command="install")

        # Handle low confidence (typo correction)
        if resolution.confidence < 0.9 and resolution.confidence > 0:
            if resolution.from_fuzzy:
                display.offline_banner()

            suggestions = [resolution.package] + resolution.alternatives
            corrected = prompts.did_you_mean(pkg_name, suggestions, display)
            if corrected is None:
                display.warning(f"Skipping {pkg_name}.")
                continue
            if corrected != resolution.package:
                resolution = resolver.resolve(corrected, command="install")

        # Handle zero confidence (not found)
        if resolution.confidence == 0:
            display.error(f"Could not resolve package: {pkg_name}")
            if resolution.notes:
                display.muted(resolution.notes)
            all_succeeded = False
            continue

        # Override source if specified
        if args.source:
            resolution.source = args.source
            resolution.trust_tier = PackageResolver._source_to_tier(args.source)
        if args.version:
            resolution.requested_version = args.version
            
        resolution.force = getattr(args, 'force', False)

        # Execute install
        try:
            result = executor.install(
                resolution,
                dry_run=args.dry_run,
                auto_yes=args.yes,
            )
            # Log successful or gracefully failed execution to audit trail
            if not args.dry_run:
                audit.log(
                    action="install",
                    package=resolution.package,
                    version=resolution.version,
                    source=resolution.source,
                    source_tier=resolution.trust_tier,
                    ai_confidence=resolution.confidence,
                    success=result.success,
                    command=result.command,
                )
            all_succeeded = all_succeeded and result.success
        except Exception as e:
            # Log unexpected crashes to audit trail
            if not args.dry_run:
                audit.log(
                    action="install",
                    package=resolution.package,
                    version=resolution.version,
                    source=resolution.source,
                    source_tier=resolution.trust_tier,
                    ai_confidence=resolution.confidence,
                    success=False,
                    command="",
                    details=f"CRASH: {str(e)}",
                )
            raise

    return 0 if all_succeeded else 1
