"""
sapt.commands.explain
Handler for 'sapt explain <tool>'.
"""


def handle_explain(args, config, display):
    """Handle 'sapt explain <tool>'."""
    from sapt.ai.providers import get_provider

    display.banner_mini()
    provider = get_provider(config)

    prompt = (
        f"Explain the Linux tool/package '{args.tool}' in plain language. "
        f"Cover: what it does, what permissions it needs, typical resource usage, "
        f"and who typically uses it. Keep it concise (3-5 sentences). "
        f'Respond in JSON: {{"name": "", "description": "", '
        f'"permissions": "", "use_case": ""}}'
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

    from sapt.ui.themes import ICONS

    display.console.print(
        Panel(
            content,
            title=f"{ICONS['brain']} Explain: {args.tool}",
            border_style=COLORS["primary"],
            box=box.ROUNDED,
            padding=(1, 2),
        )
    )

    return 0
