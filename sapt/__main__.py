"""
sapt.__main__
Main entry point — dispatches CLI commands to handlers.
Run with: python -m sapt or just 'sapt' after pip install.
"""

import sys
import json

from sapt import __version__
from sapt.cli import parse_args
from sapt.ui.display import Display
from sapt.ui.themes import ICONS
from sapt.config.manager import ConfigManager
from sapt.config.wizard import run_wizard
from sapt.security.audit import AuditLogger
from sapt.utils.system import ensure_directories
from sapt.utils.constants import PROVIDER_CONFIGS


def main():
    """Main entry point for sapt."""
    ensure_directories()

    args = parse_args()
    display = Display(
        no_color=getattr(args, "no_color", False),
        quiet=getattr(args, "json", False),
    )

    try:
        # Config command doesn't need AI setup
        if args.command == "config":
            return handle_config(args, display)

        # History doesn't need AI either
        if args.command == "history":
            return handle_history(args, display)

        # Only explanatory/generative commands require an AI provider.
        # Install and search can fall back to the local package index, while
        # native APT operations remain usable without any AI setup.
        config_mgr = ConfigManager()
        provider_required_commands = {"explain", "learn", "ask", "agent"}
        if args.command not in provider_required_commands:
            config = {}
            if config_mgr.exists():
                try:
                    config = config_mgr.load()
                except ValueError:
                    # Native and offline-capable commands do not depend on a
                    # healthy AI configuration.
                    pass
        elif not config_mgr.exists():
            display.banner()
            display.info("First time? Let's set up your AI provider.\n")
            config = run_wizard()
            if config is None:
                display.error("Setup cancelled. Run 'sapt config' to try again.")
                return 1
        else:
            try:
                config = config_mgr.load()
            except (ValueError, FileNotFoundError) as e:
                display.error(str(e))
                return 1

        # Dispatch to command handler
        handler = COMMAND_HANDLERS.get(args.command)
        if handler:
            return handler(args, config, display)
        else:
            display.error(f"Unknown command: {args.command}")
            return 1

    except KeyboardInterrupt:
        display.console.print("\n")
        display.warning("Interrupted by user.")
        return 130


# ── Command Handlers ─────────────────────────────────────────────

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
            display.info(f"Alias [sapt.package]{pkg_name}[/] → [sapt.package]{alias_target}[/]")
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

        # Execute install
        result = executor.install(
            resolution,
            dry_run=args.dry_run,
            auto_yes=args.yes,
        )

        # Log to audit trail
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

    return 0 if all_succeeded else 1


def handle_remove(args, config, display):
    """Handle 'sapt remove <package>'."""
    from sapt.execution.executor import Executor

    display.banner_mini()
    executor = Executor(display=display)
    audit = AuditLogger()

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


def handle_update(args, config, display):
    """Handle 'sapt update'."""
    from sapt.execution.executor import Executor

    display.banner_mini()
    executor = Executor(display=display)
    audit = AuditLogger()

    result = executor.update()

    audit.log(
        action="update",
        success=result.success,
        command=result.command,
    )

    return 0 if result.success else 1


def handle_upgrade(args, config, display):
    """Handle 'sapt upgrade'."""
    from sapt.execution.executor import Executor

    display.banner_mini()
    executor = Executor(display=display)
    audit = AuditLogger()

    result = executor.upgrade(auto_yes=args.yes)

    audit.log(
        action="upgrade",
        success=result.success,
        command=result.command,
    )

    return 0 if result.success else 1


def handle_search(args, config, display):
    """Handle 'sapt search <query>'."""
    from sapt.ai.resolver import PackageResolver
    from sapt.execution.apt import AptBackend

    display.banner_mini()
    query = " ".join(args.query)

    # Try AI-powered search first
    resolver = PackageResolver(config)

    with display.spinner(f"Searching for '{query}'..."):
        resolution = resolver.resolve(query, command="search")

    display.console.print()

    if resolution.confidence > 0:
        display.info(f"AI suggests: [bold cyan]{resolution.package}[/]")
        if resolution.alternatives:
            display.info("Also consider: " + ", ".join(
                f"[cyan]{a}[/]" for a in resolution.alternatives
            ))
        if resolution.notes:
            display.muted(resolution.notes)
        display.console.print()

    # Also show apt search results
    try:
        apt = AptBackend()
        results = apt.search(query)
        if results:
            from rich.table import Table
            from rich import box
            table = Table(
                title=f"{ICONS['search']} APT Results for '{query}'",
                box=box.ROUNDED, border_style="#7C3AED",
            )
            table.add_column("Package", style="bold cyan")
            table.add_column("Description")
            for r in results[:10]:
                table.add_row(r["name"], r["description"])
            display.console.print(table)
    except Exception:
        pass

    return 0


def handle_explain(args, config, display):
    """Handle 'sapt explain <tool>'."""
    from sapt.ai.providers import get_provider

    display.banner_mini()
    provider = get_provider(config)

    prompt = (
        f"Explain the Linux tool/package '{args.tool}' in plain language. "
        f"Cover: what it does, what permissions it needs, typical resource usage, "
        f"and who typically uses it. Keep it concise (3-5 sentences). "
        f"Respond in JSON: {{\"name\": \"\", \"description\": \"\", "
        f"\"permissions\": \"\", \"use_case\": \"\"}}"
    )

    with display.spinner(f"Looking up {args.tool}..."):
        try:
            result = provider.call(
                "You are a Linux tools expert. Respond ONLY with valid JSON.",
                prompt,
            )
        except Exception as e:
            display.error(f"AI lookup failed: {e}")
            return 1

    from rich.panel import Panel
    from rich import box
    from sapt.ui.themes import COLORS

    content = (
        f"[bold]{result.get('name', args.tool)}[/]\n\n"
        f"{result.get('description', 'No description available.')}\n\n"
        f"[bold]Permissions:[/] {result.get('permissions', 'N/A')}\n"
        f"[bold]Use case:[/] {result.get('use_case', 'N/A')}"
    )

    display.console.print(Panel(
        content, title=f"{ICONS['brain']} Explain: {args.tool}",
        border_style=COLORS["primary"], box=box.ROUNDED,
        padding=(1, 2),
    ))

    return 0


def handle_learn(args, config, display):
    """Handle 'sapt learn <tool>'."""
    from sapt.ai.providers import get_provider

    display.banner_mini()
    provider = get_provider(config)

    prompt = (
        f"Teach me about the Linux tool '{args.tool}'. Provide: "
        f"1) One-line description, 2) How to install it, "
        f"3) 5 most common commands/usage examples, 4) Official docs URL. "
        f"Respond in JSON: {{\"name\": \"\", \"description\": \"\", "
        f"\"install\": \"\", \"commands\": [\"\", ...], \"docs_url\": \"\"}}"
    )

    with display.spinner(f"Learning about {args.tool}..."):
        try:
            result = provider.call(
                "You are a Linux tools tutor. Respond ONLY with valid JSON.",
                prompt,
            )
        except Exception as e:
            display.error(f"AI lookup failed: {e}")
            return 1

    from rich.panel import Panel
    from rich import box
    from sapt.ui.themes import COLORS

    commands_text = ""
    for i, cmd in enumerate(result.get("commands", [])[:5], 1):
        commands_text += f"  {i}. [bold white]{cmd}[/]\n"

    content = (
        f"[bold]{result.get('name', args.tool)}[/]\n"
        f"{result.get('description', '')}\n\n"
        f"[bold]Install:[/] {result.get('install', f'sudo apt install {args.tool}')}\n\n"
        f"[bold]Common Commands:[/]\n{commands_text}\n"
        f"[bold]Docs:[/] {result.get('docs_url', 'N/A')}"
    )

    display.console.print(Panel(
        content, title=f"{ICONS['rocket']} Learn: {args.tool}",
        border_style=COLORS["secondary"], box=box.ROUNDED,
        padding=(1, 2),
    ))

    return 0


def handle_ask(args, config, display):
    """Handle 'sapt ask <goal>' — signature feature."""
    from sapt.ai.providers import get_provider

    display.banner_mini()
    goal = " ".join(args.goal)
    provider = get_provider(config)

    prompt = (
        f"The user wants to: {goal}\n"
        f"Suggest a complete toolkit of Linux packages/tools for this goal. "
        f"For each tool, explain briefly why it's needed. "
        f"Respond in JSON: {{\"goal\": \"\", \"tools\": ["
        f"{{\"name\": \"\", \"package\": \"\", \"why\": \"\", \"source\": \"apt\"}}]}}"
    )

    with display.spinner(f"Thinking about: {goal}..."):
        try:
            result = provider.call(
                "You are an expert Linux systems advisor. Respond ONLY with valid JSON.",
                prompt,
            )
        except Exception as e:
            display.error(f"AI lookup failed: {e}")
            return 1

    from rich.table import Table
    from rich.panel import Panel
    from rich import box
    from sapt.ui.themes import COLORS

    tools = result.get("tools", [])
    if not tools:
        display.warning("No tools suggested for this goal.")
        return 0

    table = Table(box=box.SIMPLE_HEAVY, border_style=COLORS["primary"])
    table.add_column("#", style="dim", width=3)
    table.add_column("Tool", style="bold cyan")
    table.add_column("Package", style="bold")
    table.add_column("Why", max_width=50)

    for i, tool in enumerate(tools, 1):
        table.add_row(
            str(i),
            tool.get("name", ""),
            tool.get("package", ""),
            tool.get("why", ""),
        )

    display.console.print(Panel(
        table,
        title=f"{ICONS['brain']} Toolkit for: {goal}",
        border_style=COLORS["primary"],
        box=box.ROUNDED,
        padding=(1, 1),
    ))

    display.console.print()
    display.info(
        "To install all: [bold]sapt install "
        + " ".join(t.get("package", "") for t in tools if t.get("package"))
        + "[/]"
    )
    display.console.print()

    return 0


def handle_doctor(args, config, display):
    """Handle 'sapt doctor'."""
    import shutil
    from sapt.execution.apt import AptBackend
    from sapt.security.audit import AuditLogger
    from sapt.ai.cache import ResponseCache
    from sapt.ai.usage import UsageTracker
    from sapt.utils.constants import CACHE_DIR

    display.banner_mini()
    checks = {}
    score = 100

    # Check APT
    try:
        apt = AptBackend()
        checks["APT available"] = {"ok": True, "detail": "apt is installed and working"}
    except Exception:
        checks["APT available"] = {"ok": False, "detail": "apt not found"}
        score -= 20

    # Check audit log
    audit = AuditLogger()
    valid, msg = audit.verify_chain()
    checks["Audit log integrity"] = {"ok": valid, "detail": msg}
    if not valid:
        score -= 15

    # Check cache
    cache = ResponseCache()
    stats = cache.stats()
    checks["AI response cache"] = {
        "ok": True,
        "detail": f"{stats['entries']} entries, {stats['size_kb']} KB",
    }

    usage = UsageTracker().monthly_summary()
    budget = float(config.get("monthly_budget_usd") or 0.0) if config else 0.0
    usage_detail = (
        f"{usage['calls']} calls, ${usage['estimated_spend_usd']:.4f} estimated this month"
    )
    if budget > 0:
        usage_detail += f" / ${budget:.4f} budget"
    checks["AI usage budget"] = {
        "ok": budget <= 0 or usage["estimated_spend_usd"] <= budget,
        "detail": usage_detail,
    }
    if budget > 0 and usage["estimated_spend_usd"] > budget:
        score -= 10

    # Check config
    config_mgr = ConfigManager()
    if not config_mgr.exists():
        checks["Config file"] = {"ok": False, "detail": "No config found"}
        score -= 10
    else:
        try:
            config_mgr.load()
            checks["Config file"] = {"ok": True, "detail": "Config exists and is valid"}
        except (ValueError, FileNotFoundError):
            checks["Config file"] = {"ok": False, "detail": "Config exists but is invalid"}
            score -= 10

    # Check disk usage of cache dir
    cache_size = sum(
        f.stat().st_size for f in CACHE_DIR.rglob("*") if f.is_file()
    ) if CACHE_DIR.exists() else 0
    cache_mb = cache_size / (1024 * 1024)
    checks["Cache disk usage"] = {
        "ok": cache_mb < 100,
        "detail": f"{cache_mb:.1f} MB" + (" (consider clearing)" if cache_mb > 100 else ""),
    }
    if cache_mb > 100:
        score -= 5

    report = {"score": max(0, score), "checks": checks}
    if args.json:
        _emit_json(report)
    else:
        display.show_doctor(report)
    return 0


def handle_history(args, display):
    """Handle 'sapt history'."""
    display.banner_mini()
    audit = AuditLogger()

    if args.verify:
        with display.spinner("Verifying audit log integrity..."):
            valid, message = audit.verify_chain()
        if args.json:
            _emit_json({"valid": valid, "message": message})
        elif valid:
            display.success(message)
        else:
            display.error(message)
        return 0 if valid else 1

    entries = audit.get_history(args.count)
    if args.json:
        _emit_json({"entries": entries, "total_entries": audit.entry_count()})
        return 0
    if not entries:
        display.info("No history yet. Start by installing something!")
        return 0

    display.show_history(entries)
    display.muted(f"  {audit.entry_count()} total entries in audit log.")
    display.console.print()
    return 0


def handle_why(args, config, display):
    """Handle 'sapt why <package>' using APT reverse dependencies."""
    from rich import box
    from rich.table import Table
    from sapt.execution.apt import AptBackend

    if not args.json:
        display.banner_mini()
    apt = AptBackend()
    package = args.package

    if not apt.is_installed(package):
        if args.json:
            _emit_json({"package": package, "installed": False, "reverse_dependencies": []})
            return 1
        display.warning(f"[sapt.package]{package}[/] is not installed.")
        return 1

    version = apt.get_version(package) or "unknown version"
    reverse_deps = apt.get_reverse_dependencies(package)
    if args.json:
        _emit_json({
            "package": package, "installed": True, "version": version,
            "reverse_dependencies": reverse_deps,
        })
        return 0
    if not reverse_deps:
        display.info(
            f"No installed reverse dependencies were reported for "
            f"[sapt.package]{package}[/] ({version})."
        )
        return 0

    table = Table(
        title=f"{ICONS['link']} Packages depending on {package}",
        box=box.ROUNDED, border_style="#7C3AED",
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("Package", style="bold cyan")
    for index, dependent in enumerate(reverse_deps, 1):
        table.add_row(str(index), dependent)
    display.console.print(table)
    display.muted(
        f"  {len(reverse_deps)} package(s) may depend on {package} "
        "according to APT metadata."
    )
    return 0


def handle_diff(args, config, display):
    """Handle 'sapt diff' from SmartAPT's append-only audit history."""
    from rich import box
    from rich.table import Table

    if not args.json:
        display.banner_mini()
    entries = AuditLogger().get_history(args.count)
    changes = [
        entry for entry in entries
        if entry.get("action") in {"install", "remove", "purge", "upgrade"}
    ]
    if args.json:
        _emit_json({"changes": list(reversed(changes))})
        return 0
    if not changes:
        display.info("No package changes recorded in the selected history.")
        return 0

    symbols = {"install": "+", "remove": "-", "purge": "-", "upgrade": "↑"}
    table = Table(
        title=f"{ICONS['chart']} Recorded Package Changes",
        box=box.ROUNDED, border_style="#7C3AED",
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


def _emit_json(data):
    """Write a single JSON document for a non-interactive report command."""
    sys.stdout.write(json.dumps(data, ensure_ascii=False, default=str) + "\n")


def handle_undo(args, config, display):
    """Reverse the latest successful, reversible package action."""
    from sapt.ai.resolver import PackageResolution
    from sapt.execution.executor import Executor

    display.banner_mini()
    audit = AuditLogger()
    reversible = {"install", "remove", "purge"}
    target = next(
        (
            entry for entry in reversed(audit.get_all())
            if entry.get("success") and entry.get("action") in reversible
            and entry.get("package")
        ),
        None,
    )
    if target is None:
        display.info("No successful install, remove, or purge action is available to undo.")
        return 0

    package = target["package"]
    action = target["action"]
    executor = Executor(display=display)
    if action == "install":
        display.info(f"Undoing install of [sapt.package]{package}[/] by removing it.")
        result = executor.remove(
            package, dry_run=args.dry_run, auto_yes=args.yes,
        )
        inverse = "remove"
    else:
        display.warning(
            f"Undoing {action} reinstalls the currently available APT version; "
            "the removed version may no longer be available."
        )
        resolution = PackageResolution(
            package=package, source="apt", confidence=1.0, trust_tier=1,
            notes="Reinstalled while undoing a previous SmartAPT action.",
        )
        result = executor.install(
            resolution, dry_run=args.dry_run, auto_yes=args.yes,
        )
        inverse = "install"

    if not args.dry_run:
        audit.log(
            action="undo", package=package, source="apt", source_tier=1,
            success=result.success, command=result.command,
            details=f"Reversed {action} entry {target.get('id', 'unknown')} via {inverse}.",
        )
    return 0 if result.success else 1


def handle_agent(args, config, display):
    """Recommend and safely install a small, goal-specific APT toolkit."""
    from rich import box
    from rich.table import Table
    from sapt.ai.providers import get_provider
    from sapt.ai.resolver import PackageResolution
    from sapt.ai.sanitizer import InputSanitizer, SanitizationError
    from sapt.execution.executor import Executor

    display.banner_mini()
    goal = " ".join(args.goal)
    try:
        goal = InputSanitizer().check(goal)
    except SanitizationError as error:
        display.error(f"Goal rejected: {error}")
        return 1

    prompt = (
        f"Goal: {goal}\n"
        "Recommend at most 10 packages available from the official Debian/Ubuntu "
        "APT repositories. Do not include shell commands, URLs, PPAs, Snap, "
        "Flatpak, or GitHub releases. Respond only with JSON in this schema: "
        '{"tools":[{"package":"exact_apt_package_name","why":"short reason"}]}'
    )
    with display.spinner(f"Planning toolkit for: {goal}..."):
        try:
            response = get_provider(config).call(
                "You are a conservative Linux package advisor. Return only valid JSON.",
                prompt,
            )
        except Exception as error:
            display.error(f"AI planning failed: {error}")
            return 1

    raw_tools = response.get("tools", []) if isinstance(response, dict) else []
    sanitizer = InputSanitizer()
    tools = []
    for tool in raw_tools[:10]:
        if not isinstance(tool, dict):
            continue
        try:
            package = sanitizer.check_package_name(str(tool.get("package", "")))
        except SanitizationError:
            continue
        if package not in {item["package"] for item in tools}:
            tools.append({"package": package, "why": str(tool.get("why", ""))})

    if not tools:
        display.warning("No safe APT package recommendations were returned for this goal.")
        return 1

    table = Table(
        title=f"{ICONS['brain']} APT Toolkit for: {goal}",
        box=box.ROUNDED, border_style="#7C3AED",
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("Package", style="bold cyan")
    table.add_column("Why")
    for index, tool in enumerate(tools, 1):
        table.add_row(str(index), tool["package"], tool["why"])
    display.console.print(table)

    executor = Executor(display=display)
    audit = AuditLogger()
    successes = 0
    for tool in tools:
        resolution = PackageResolution(
            package=tool["package"], source="apt", confidence=1.0,
            trust_tier=1, notes=tool["why"],
        )
        result = executor.install(
            resolution, dry_run=args.dry_run, auto_yes=args.yes,
        )
        if not args.dry_run:
            audit.log(
                action="install", package=resolution.package,
                version=resolution.version, source="apt", source_tier=1,
                ai_confidence=1.0, success=result.success, command=result.command,
                details=f"Agent goal: {goal}",
            )
        successes += int(result.success)

    if successes == len(tools):
        display.success(f"Agent completed {successes}/{len(tools)} package actions.")
        return 0
    display.warning(f"Agent completed {successes}/{len(tools)} package actions.")
    return 1


def handle_cache(args, config, display):
    """Inspect or explicitly clear the local AI response cache."""
    from sapt.ai.cache import ResponseCache

    cache = ResponseCache()
    if args.clear:
        deleted = cache.clear()
        payload = {"cleared": deleted}
        if args.json:
            _emit_json(payload)
        else:
            display.success(f"Cleared {deleted} cached AI response(s).")
        return 0

    stats = cache.stats()
    if args.json:
        _emit_json(stats)
    else:
        display.info(
            f"AI cache: {stats['entries']} entries, {stats['total_hits']} hits, "
            f"{stats['size_kb']} KB, {stats['ttl_hours']:.0f}h TTL."
        )
    return 0


def handle_audit(args, config, display):
    """Summarize and verify the tamper-evident audit log."""
    from collections import Counter
    from rich import box
    from rich.table import Table

    audit = AuditLogger()
    valid, message = audit.verify_chain()
    entries = audit.get_all()
    actions = Counter(entry.get("action", "unknown") for entry in entries)
    sources = Counter(entry.get("source", "unknown") for entry in entries)
    successes = sum(1 for entry in entries if entry.get("success"))
    failures = len(entries) - successes
    recent_entries = audit.get_history(args.count) if args.entries else []

    report = {
        "valid": valid,
        "message": message,
        "total_entries": len(entries),
        "successes": successes,
        "failures": failures,
        "actions": dict(sorted(actions.items())),
        "sources": dict(sorted(sources.items())),
    }
    if args.entries:
        report["entries"] = recent_entries
    cve_packages_arg = getattr(args, "cve", None)
    if cve_packages_arg is not None:
        from sapt.security.vulnerabilities import VulnerabilityScanner

        packages = cve_packages_arg or [
            entry.get("package", "")
            for entry in reversed(entries)
            if entry.get("success") and entry.get("package")
        ][:10]
        scanner = VulnerabilityScanner()
        cve_reports = [scanner.scan(package).to_dict() for package in packages]
        report["vulnerabilities"] = cve_reports

    if args.json:
        _emit_json(report)
        return 0 if valid else 1

    display.banner_mini()
    if valid:
        display.success(message)
    else:
        display.error(message)

    table = Table(
        title=f"{ICONS['shield']} Audit Summary",
        box=box.ROUNDED,
        border_style="#7C3AED",
    )
    table.add_column("Metric", style="bold")
    table.add_column("Value")
    table.add_row("Total entries", str(len(entries)))
    table.add_row("Successful actions", str(successes))
    table.add_row("Failed actions", str(failures))
    table.add_row(
        "Actions",
        ", ".join(f"{name}: {count}" for name, count in sorted(actions.items())) or "none",
    )
    table.add_row(
        "Sources",
        ", ".join(f"{name}: {count}" for name, count in sorted(sources.items())) or "none",
    )
    display.console.print(table)

    if cve_packages_arg is not None:
        vuln_reports = report.get("vulnerabilities", [])
        if not vuln_reports:
            display.info("No packages selected for CVE checks.")
        else:
            vuln_table = Table(
                title=f"{ICONS['shield']} OSV Vulnerability Checks",
                box=box.ROUNDED,
                border_style="#7C3AED",
            )
            vuln_table.add_column("Package", style="bold cyan")
            vuln_table.add_column("Status")
            vuln_table.add_column("Findings")
            for item in vuln_reports:
                if not item.get("ok"):
                    status = "lookup failed"
                    findings = item.get("error", "")
                elif item.get("vulnerable"):
                    status = "vulnerable"
                    findings = ", ".join(
                        vuln.get("id", "unknown")
                        for vuln in item.get("vulnerabilities", [])[:5]
                    )
                else:
                    status = "no known vulns"
                    findings = "clean"
                vuln_table.add_row(item.get("package", ""), status, findings)
            display.console.print(vuln_table)

    if args.entries and recent_entries:
        display.show_history(recent_entries)
    return 0 if valid else 1


def handle_completion(args, config, display):
    """Print a static shell completion script for the installed CLI."""
    commands = [
        "install", "remove", "update", "upgrade", "search", "explain",
        "learn", "ask", "doctor", "history", "audit", "completion", "why",
        "diff", "undo", "agent", "cache", "alias", "config",
    ]
    options = {
        "install": "--dry-run --source --version --yes -y",
        "remove": "--clean --yes -y",
        "upgrade": "--yes -y",
        "history": "--count -n --verify",
        "audit": "--count -n --entries --cve --json",
        "completion": "bash zsh fish",
        "diff": "--count -n",
        "undo": "--dry-run --yes -y",
        "agent": "--dry-run --yes -y",
        "cache": "--stats --clear",
        "alias": "--remove --list",
        "config": "--show --set-provider --set-model --set-key --set-endpoint --set-budget --set-call-cost --usage --reset --json",
    }
    script = _completion_script(args.shell, commands, options)
    sys.stdout.write(script)
    if not script.endswith("\n"):
        sys.stdout.write("\n")
    return 0


def _completion_script(shell: str, commands: list[str], options: dict[str, str]) -> str:
    command_words = " ".join(commands)
    if shell == "bash":
        cases = "\n".join(
            f'            {command}) COMPREPLY=( $(compgen -W "{words}" -- "$cur") ) ;;'
            for command, words in sorted(options.items())
        )
        return f"""# sapt bash completion
_sapt_complete()
{{
    local cur command
    COMPREPLY=()
    cur="${{COMP_WORDS[COMP_CWORD]}}"
    command="${{COMP_WORDS[1]}}"

    if [[ $COMP_CWORD -eq 1 ]]; then
        COMPREPLY=( $(compgen -W "{command_words}" -- "$cur") )
        return 0
    fi

    case "$command" in
{cases}
    esac
}}
complete -F _sapt_complete sapt
"""
    if shell == "zsh":
        zsh_commands = " ".join(f"{command}:command" for command in commands)
        zsh_cases = "\n".join(
            f'    {command}) _arguments "*:: :(({words}))" ;;'
            for command, words in sorted(options.items())
        )
        return f"""#compdef sapt
_sapt()
{{
  local -a commands
  commands=({zsh_commands})
  if (( CURRENT == 2 )); then
    _describe -t commands 'sapt command' commands
    return
  fi
  case $words[2] in
{zsh_cases}
  esac
}}
_sapt "$@"
"""
    fish_options = "\n".join(
        f"complete -c sapt -n '__fish_seen_subcommand_from {command}' -f -a '{words}'"
        for command, words in sorted(options.items())
    )
    return f"""# sapt fish completion
complete -c sapt -f -a '{command_words}'
{fish_options}
"""


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
                _emit_json({"aliases": aliases})
            elif aliases:
                for name, package in aliases.items():
                    display.info(f"[sapt.package]{name}[/] → [sapt.package]{package}[/]")
            else:
                display.info("No aliases configured.")
            return 0

        if not args.package:
            target = manager.resolve(args.name)
            if args.json:
                _emit_json({"alias": args.name, "package": target})
            elif target:
                display.info(f"[sapt.package]{args.name}[/] → [sapt.package]{target}[/]")
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


def handle_config(args, display):
    """Handle 'sapt config' subcommand."""
    config_mgr = ConfigManager()

    if args.show:
        if not config_mgr.exists():
            display.error("No config found. Run 'sapt config' to set up.")
            return 1
        display.banner_mini()
        config = config_mgr.show()
        from rich.table import Table
        from rich import box
        table = Table(box=box.ROUNDED, border_style="#7C3AED",
                      title=f"{ICONS['gear']} Current Configuration")
        table.add_column("Setting", style="bold")
        table.add_column("Value")
        for key, value in config.items():
            if key not in ("api_key_encrypted", "_encrypted", "version"):
                table.add_row(key, str(value))
        display.console.print(table)
        return 0

    if args.reset:
        config_mgr.reset()
        display.success("Config deleted. Run 'sapt config' for fresh setup.")
        return 0

    if args.usage:
        from sapt.ai.usage import UsageTracker
        from rich.table import Table
        from rich import box

        summary = UsageTracker().monthly_summary()
        if args.json:
            _emit_json(summary)
            return 0
        table = Table(
            box=box.ROUNDED,
            border_style="#7C3AED",
            title=f"{ICONS['chart']} AI Usage ({summary['month']})",
        )
        table.add_column("Metric", style="bold")
        table.add_column("Value")
        table.add_row("Calls", str(summary["calls"]))
        table.add_row("Successes", str(summary["successes"]))
        table.add_row("Failures", str(summary["failures"]))
        table.add_row("Estimated spend", f"${summary['estimated_spend_usd']:.4f}")
        display.console.print(table)
        return 0

    if args.set_budget is not None or args.set_call_cost is not None:
        if not config_mgr.exists():
            display.error("No config found. Run 'sapt config' to set up first.")
            return 1
        if args.set_budget is not None:
            if args.set_budget < 0:
                display.error("Budget must be zero or greater.")
                return 1
            config_mgr.set("monthly_budget_usd", f"{args.set_budget:.6f}")
            display.success(f"Monthly AI budget set to ${args.set_budget:.4f}.")
        else:
            if args.set_call_cost < 0:
                display.error("Estimated call cost must be zero or greater.")
                return 1
            config_mgr.set("estimated_cost_per_call_usd", f"{args.set_call_cost:.6f}")
            display.success(f"Estimated AI call cost set to ${args.set_call_cost:.6f}.")
        return 0

    if args.set_key:
        import questionary
        new_key = questionary.password("Enter new API key:").ask()
        if new_key:
            config_mgr.set("api_key", new_key.strip())
            display.success("API key updated.")
        return 0

    if args.set_provider:
        # A provider change also needs its model, endpoint, and key, so the
        # setup wizard is the safest way to collect a complete configuration.
        run_wizard()
        return 0

    if args.set_model or args.set_endpoint:
        if not config_mgr.exists():
            display.error("No config found. Run 'sapt config' to set up first.")
            return 1

        import questionary
        config = config_mgr.load()
        if args.set_model:
            provider = config.get("provider", "custom")
            models = PROVIDER_CONFIGS.get(provider, {}).get("models", [])
            if models:
                value = questionary.select(
                    "Select model:", choices=models,
                    default=config.get("model"),
                ).ask()
            else:
                value = questionary.text(
                    "Enter model name:", default=config.get("model", ""),
                ).ask()
            key, label = "model", "Model"
        else:
            value = questionary.text(
                "Enter API endpoint URL:", default=config.get("endpoint", ""),
            ).ask()
            key, label = "endpoint", "Endpoint"

        if value:
            config_mgr.set(key, value.strip())
            display.success(f"{label} updated.")
        return 0

    # Default: run full wizard
    run_wizard()
    return 0


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
}


if __name__ == "__main__":
    sys.exit(main() or 0)
