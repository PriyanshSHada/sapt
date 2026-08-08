"""
sapt.commands.learn
Handler for 'sapt learn <tool>'.
"""


def handle_learn(args, config, display):
    """Handle 'sapt learn <tool>'."""
    from sapt.ai.providers import get_provider

    display.banner_mini()
    provider = get_provider(config)

    prompt = (
        f"Teach me about the Linux tool '{args.tool}'. Provide: "
        f"1) One-line description, 2) How to install it, "
        f"3) 5 most common commands/usage examples, 4) Official docs URL. "
        f'Respond in JSON: {{"name": "", "description": "", '
        f'"install": "", "commands": ["", ...], "docs_url": ""}}'
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
    from sapt.ui.themes import COLORS, ICONS

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

    display.console.print(
        Panel(
            content,
            title=f"{ICONS['rocket']} Learn: {args.tool}",
            border_style=COLORS["secondary"],
            box=box.ROUNDED,
            padding=(1, 2),
        )
    )

    return 0
