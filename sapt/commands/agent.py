"""
sapt.commands.agent
Handler for 'sapt agent <goal>'.
"""

from sapt.security.audit import AuditLogger
from sapt.ui.themes import ICONS


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
        display.warning(
            "No safe APT package recommendations were returned for this goal."
        )
        return 1

    table = Table(
        title=f"{ICONS['brain']} APT Toolkit for: {goal}",
        box=box.ROUNDED,
        border_style="#7C3AED",
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
            package=tool["package"],
            source="apt",
            confidence=1.0,
            trust_tier=1,
            notes=tool["why"],
        )
        result = executor.install(
            resolution,
            dry_run=args.dry_run,
            auto_yes=args.yes,
        )
        if not args.dry_run:
            audit.log(
                action="install",
                package=resolution.package,
                version=resolution.version,
                source="apt",
                source_tier=1,
                ai_confidence=1.0,
                success=result.success,
                command=result.command,
                details=f"Agent goal: {goal}",
            )
        successes += int(result.success)

    if successes == len(tools):
        display.success(f"Agent completed {successes}/{len(tools)} package actions.")
        return 0
    display.warning(f"Agent completed {successes}/{len(tools)} package actions.")
    return 1
