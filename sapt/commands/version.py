"""
sapt.commands.version
Package version management commands.
"""

from sapt.security.audit import AuditLogger
from sapt.ui.themes import ICONS


def handle_version(args, config, display):
    """Handle package version operations."""
    from sapt.execution.apt import AptBackend
    
    display.banner_mini()
    apt = AptBackend()
    package = args.package
    
    if args.list:
        # List all available versions
        versions = apt.get_all_versions(package)
        if not versions:
            display.warning(f"No versions found for package: {package}")
            return 1
        
        current_version = apt.get_version(package)
        
        from rich.table import Table
        from rich import box
        
        table = Table(
            title=f"{ICONS['tag']} Versions for {package}",
            box=box.ROUNDED,
            border_style="#7C3AED",
        )
        table.add_column("Version", style="bold")
        table.add_column("Source", style="dim")
        table.add_column("Status")
        
        for version_info in versions:
            version = version_info.get("version", "")
            source = version_info.get("source", "apt")
            status = ""
            
            if version == current_version:
                status = f"{ICONS['check']} Installed"
            elif version_info.get("candidate", False):
                status = f"{ICONS['upgrade']} Candidate"
            
            table.add_row(version, source, status)
        
        display.console.print(table)
        return 0
    
    if args.show:
        # Show current version info
        version = apt.get_version(package)
        if not version:
            display.warning(f"Package not installed: {package}")
            return 1
        
        display.success(f"{package} is installed at version {version}")
        
        # Check for available updates
        candidate = apt.get_candidate_version(package)
        if candidate and candidate != version:
            display.info(f"Available: {candidate} ({ICONS['upgrade']} update available)")
        
        return 0
    
    if args.pin:
        # Pin package to version
        version = args.pin
        if not apt.is_version_available(package, version):
            display.error(f"Version {version} not available for {package}")
            return 1
        
        # Pin the version
        try:
            apt.pin_package(package, version)
            display.success(f"Pinned {package} to version {version}")
            
            # Log the operation
            audit = AuditLogger()
            audit.log(
                action="pin",
                package=package,
                version=version,
                source="apt",
                source_tier=1,
                success=True,
                command=f"apt policy {package}",
                details=f"Pinned package {package} to version {version}",
            )
            return 0
        except Exception as e:
            display.error(f"Failed to pin package: {e}")
            return 1
    
    if args.unpin:
        # Unpin package
        try:
            apt.unpin_package(package)
            display.success(f"Unpinned {package}")
            
            # Log the operation
            audit = AuditLogger()
            audit.log(
                action="unpin",
                package=package,
                version="",
                source="apt",
                source_tier=1,
                success=True,
                command="apt policy",
                details=f"Unpinned package {package}",
            )
            return 0
        except Exception as e:
            display.error(f"Failed to unpin package: {e}")
            return 1
    
    # Default: show version
    version = apt.get_version(package)
    if version:
        display.success(f"{package} is installed at version {version}")
        return 0
    else:
        display.warning(f"Package not installed: {package}")
        return 1