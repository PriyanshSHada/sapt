"""
sapt.commands.search
Handler for 'sapt search <query>'.
"""

from sapt.ui.themes import ICONS


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
            display.info(
                "Also consider: "
                + ", ".join(f"[cyan]{a}[/]" for a in resolution.alternatives)
            )
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
                box=box.ROUNDED,
                border_style="#7C3AED",
            )
            table.add_column("Package", style="bold cyan")
            table.add_column("Description")
            for r in results[:10]:
                table.add_row(r["name"], r["description"])
            display.console.print(table)
    except Exception:
        pass

    return 0
