"""
sapt.commands.ask
Handler for 'sapt ask <goal>' — signature feature.
"""

from sapt.ui.themes import ICONS


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
        f'Respond in JSON: {{"goal": "", "tools": ['
        f'{{"name": "", "package": "", "why": "", "source": "apt"}}]}}'
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

    display.console.print(
        Panel(
            table,
            title=f"{ICONS['brain']} Toolkit for: {goal}",
            border_style=COLORS["primary"],
            box=box.ROUNDED,
            padding=(1, 1),
        )
    )

    display.console.print()
    display.info(
        "To install all: [bold]sapt install "
        + " ".join(t.get("package", "") for t in tools if t.get("package"))
        + "[/]"
    )
    display.console.print()

    return 0
