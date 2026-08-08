"""
sapt.commands.list_cmd
Handler for 'sapt list'.
"""

from sapt.commands._helpers import emit_json
from sapt.ui.themes import ICONS


def handle_list(args, config, display):
    """List packages managed by SmartAPT, with optional filtering."""
    from rich import box
    from rich.table import Table
    from sapt.security.audit import AuditLogger

    if not args.json:
        display.banner_mini()

    audit = AuditLogger()
    entries = audit.get_all()

    # Play forward history to find currently installed packages
    # State maps package name to dict of details
    installed = {}
    for entry in entries:
        if not entry.get("success"):
            continue
        
        action = entry.get("action")
        pkg = entry.get("package")
        if not pkg:
            continue

        if action in ("install", "upgrade"):
            installed[pkg] = {
                "version": entry.get("version", "unknown"),
                "source": entry.get("source", "apt"),
                "timestamp": entry.get("timestamp", ""),
            }
        elif action in ("remove", "purge"):
            installed.pop(pkg, None)

    # Filter by source
    if args.source:
        installed = {
            pkg: info for pkg, info in installed.items() 
            if info["source"] == args.source
        }

    # Filter by vulnerability (heavy operation)
    vulnerabilities_map = {}
    if args.vulnerable:
        if not args.json:
            display.info("Scanning for known vulnerabilities...")
        from sapt.security.vulnerabilities import VulnerabilityScanner
        scanner = VulnerabilityScanner()
        
        vulnerable_pkgs = {}
        for pkg, info in list(installed.items()):
            report = scanner.scan(pkg, version=info["version"])
            if report.vulnerable:
                vulnerable_pkgs[pkg] = info
                vulnerabilities_map[pkg] = report
        installed = vulnerable_pkgs

    if args.json:
        payload = {
            "count": len(installed),
            "packages": [
                {
                    "package": pkg,
                    **info,
                    **({"vulnerabilities": vulnerabilities_map[pkg].to_dict()} if pkg in vulnerabilities_map else {})
                }
                for pkg, info in installed.items()
            ]
        }
        emit_json(payload)
        return 0

    if not installed:
        if args.vulnerable:
            display.success("No packages managed by SmartAPT have known vulnerabilities! 🎉")
        elif args.source:
            display.info(f"No packages managed by SmartAPT from source: {args.source}")
        else:
            display.info("No packages are currently managed by SmartAPT.")
        return 0

    # Build and show table
    title = f"{ICONS['package']} Managed Packages"
    if args.vulnerable:
        title = f"{ICONS['shield']} Vulnerable Managed Packages"
    elif args.source:
        title += f" ({args.source})"

    table = Table(
        title=title,
        box=box.ROUNDED,
        border_style="#7C3AED" if not args.vulnerable else "red",
    )
    table.add_column("Package", style="bold cyan")
    table.add_column("Version")
    table.add_column("Source")
    table.add_column("Installed")
    if args.vulnerable:
        table.add_column("CVEs", style="bold red")

    # Sort alphabetically by package name
    for pkg, info in sorted(installed.items()):
        row = [
            pkg,
            info["version"],
            info["source"],
            info["timestamp"][:10], # Just the date YYYY-MM-DD
        ]
        if args.vulnerable:
            report = vulnerabilities_map[pkg]
            cve_list = ", ".join(v.id for v in report.vulnerabilities[:3])
            if len(report.vulnerabilities) > 3:
                cve_list += f" (+{len(report.vulnerabilities)-3} more)"
            row.append(cve_list)
        table.add_row(*row)

    display.console.print(table)
    display.muted(f"  {len(installed)} package(s) found.")
    
    return 0
