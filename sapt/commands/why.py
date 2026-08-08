"""
sapt.commands.why
Handler for 'sapt why <package>'.
"""

from sapt.commands._helpers import emit_json
from sapt.ui.themes import ICONS


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
            emit_json(
                {"package": package, "installed": False, "reverse_dependencies": []}
            )
            return 1
        display.warning(f"[sapt.package]{package}[/] is not installed.")
        return 1

    version = apt.get_version(package) or "unknown version"
    reverse_deps = apt.get_reverse_dependencies(package)
    if args.json:
        emit_json(
            {
                "package": package,
                "installed": True,
                "version": version,
                "reverse_dependencies": reverse_deps,
            }
        )
        return 0
    if not reverse_deps:
        display.info(
            f"No installed reverse dependencies were reported for "
            f"[sapt.package]{package}[/] ({version})."
        )
        return 0

    table = Table(
        title=f"{ICONS['link']} Packages depending on {package}",
        box=box.ROUNDED,
        border_style="#7C3AED",
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
