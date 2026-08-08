"""
sapt.commands.audit
Handler for 'sapt audit'.
"""

from sapt.commands._helpers import emit_json
from sapt.security.audit import AuditLogger
from sapt.ui.themes import ICONS


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

        packages = (
            cve_packages_arg
            or [
                entry.get("package", "")
                for entry in reversed(entries)
                if entry.get("success") and entry.get("package")
            ][:10]
        )
        scanner = VulnerabilityScanner()
        cve_reports = [scanner.scan(package).to_dict() for package in packages]
        report["vulnerabilities"] = cve_reports

    if args.json:
        emit_json(report)
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
        ", ".join(f"{name}: {count}" for name, count in sorted(actions.items()))
        or "none",
    )
    table.add_row(
        "Sources",
        ", ".join(f"{name}: {count}" for name, count in sorted(sources.items()))
        or "none",
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
