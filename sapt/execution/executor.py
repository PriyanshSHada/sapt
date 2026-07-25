"""
sapt.execution.executor
Unified command executor — converts PackageResolution into real
system commands. This is Layer 2: deterministic, rule-based, no AI.
"""

import time
from dataclasses import dataclass

from sapt.execution.apt import AptBackend, AptError
from sapt.execution.stores import (
    FlatpakBackend,
    SnapBackend,
    GithubBackend,
    StoreBackendError,
)
from sapt.execution.validator import CommandValidator, SecurityViolation
from sapt.ai.resolver import PackageResolution
from sapt.security.verification import PackageVerifier
from sapt.ui.display import Display
from sapt.ui import prompts
from sapt.utils.system import is_interactive


@dataclass
class ExecutionResult:
    """Result of a command execution."""

    success: bool
    package: str
    command: str
    output: str = ""
    return_code: int = 0
    duration: float = 0.0
    source: str = "apt"


class Executor:
    """Converts AI resolutions into safe system commands and executes them.

    This is the ONLY layer that touches the system. It:
    1. Validates commands against the allowlist
    2. Shows confirmation prompts
    3. Executes via the APT backend
    4. Returns structured results for audit logging
    """

    def __init__(self, display: Display | None = None):
        self.apt = AptBackend()
        self.validator = CommandValidator()
        self.verifier = PackageVerifier()
        self.display = display or Display()

    def install(
        self,
        resolution: PackageResolution,
        dry_run: bool = False,
        auto_yes: bool = False,
    ) -> ExecutionResult:
        """Execute a package install from a resolution."""
        package = resolution.package
        requested_version = resolution.requested_version
        install_target = (
            f"{package}={requested_version}" if requested_version else package
        )
        command = f"apt install -y {install_target}"

        if resolution.source != "apt":
            if resolution.source in {"snap", "flatpak", "github"}:
                return self._install_store(
                    resolution, dry_run=dry_run, auto_yes=auto_yes
                )
            message = (
                f"Source '{resolution.source}' is not supported by this build. "
                "Only apt, snap, flatpak, and github packages can be installed currently."
            )
            self.display.error(message)
            return ExecutionResult(
                success=False,
                package=package,
                command="",
                output=message,
                source=resolution.source,
            )

        verification = self.verifier.verify(package, resolution.source)
        resolution.trust_tier = verification.tier
        for warning in verification.warnings:
            self.display.warning(warning)

        # Validate
        try:
            self.validator.validate(command)
            self.validator.validate_package_name(package)
            if requested_version:
                self.validator.validate_version(requested_version)
        except SecurityViolation as e:
            self.display.error(str(e))
            return ExecutionResult(
                success=False,
                package=package,
                command=command,
                output=str(e),
            )

        # Check if already installed
        if self.apt.is_installed(package):
            version = self.apt.get_version(package)
            if not requested_version or version == requested_version:
                self.display.success(
                    f"[sapt.package]{package}[/] {version or ''} is already installed."
                )
                return ExecutionResult(
                    success=True,
                    package=package,
                    command="(already installed)",
                    return_code=0,
                )

        # Get size info
        size = self.apt.get_size(package) or "unknown"
        version = self.apt.get_available_version(package) or ""
        resolution.size = size
        resolution.version = version

        # Show resolution
        self.display.show_resolution(
            {
                "package": package,
                "source": resolution.source,
                "confidence": resolution.confidence,
                "trust_tier": resolution.trust_tier,
                "version": version,
                "size": size,
                "notes": resolution.notes,
            }
        )

        # CVE Scan
        from sapt.security.vulnerabilities import VulnerabilityScanner

        scanner = VulnerabilityScanner()
        with self.display.spinner(f"Checking OSV CVE database for {package}..."):
            cve_report = scanner.scan(package, version=version)
        if not cve_report.ok:
            cve_status = "lookup failed"
            self.display.warning(f"CVE lookup failed: {cve_report.error}")
        elif cve_report.vulnerable:
            cve_status = f"{len(cve_report.vulnerabilities)} CVEs found"
            self.display.warning(
                f"[bold red]⚠️ Found {len(cve_report.vulnerabilities)} "
                f"known vulnerability(ies) for {package}:[/]"
            )
            for vuln in cve_report.vulnerabilities[:3]:
                self.display.warning(f"  - {vuln.id} ({vuln.severity})")
            if len(cve_report.vulnerabilities) > 3:
                self.display.warning(
                    f"  - ... and {len(cve_report.vulnerabilities) - 3} more."
                )
        else:
            cve_status = "no known CVEs"
        self.display.console.print()

        # Dry run — stop here
        if dry_run:
            self.display.info(
                "[dim]--dry-run:[/] No changes made. "
                f"Would run: [bold]sudo {command}[/]"
            )
            return ExecutionResult(
                success=True,
                package=package,
                command=f"sudo {command} (dry-run)",
            )

        # Confirm
        if not auto_yes:
            if not is_interactive():
                message = (
                    "Confirmation required in a non-interactive session."
                    " Use --yes or --dry-run."
                )
                self.display.error(message)
                return ExecutionResult(
                    success=False,
                    package=package,
                    command=command,
                    output=message,
                )
            confirmed = prompts.confirm_install(
                package=package,
                source=resolution.source,
                tier=resolution.trust_tier,
                size=size,
                version=version,
                cve_status=cve_status,
                display=self.display,
            )
            if not confirmed:
                self.display.warning("Installation cancelled.")
                return ExecutionResult(
                    success=False,
                    package=package,
                    command=command,
                    output="Cancelled by user.",
                )

        # Execute
        self.display.console.print()
        start = time.time()
        try:
            with self.display.spinner(f"Installing {package}..."):
                result = self.apt.install(install_target)
            duration = time.time() - start

            self.display.console.print()
            self.display.show_install_summary(
                {
                    "package": package,
                    "source": resolution.source,
                    "duration": duration,
                    "run_command": package,
                }
            )

            # Post-install hints
            if resolution.notes:
                self.display.info(f"Tip: {resolution.notes}")
                self.display.console.print()

            return ExecutionResult(
                success=True,
                package=package,
                command=f"sudo {command}",
                output=result.stdout,
                return_code=result.returncode,
                duration=duration,
                source=resolution.source,
            )

        except AptError as e:
            duration = time.time() - start
            self.display.console.print()
            self.display.error(f"Installation failed: {e}")
            return ExecutionResult(
                success=False,
                package=package,
                command=f"sudo {command}",
                output=str(e),
                return_code=1,
                duration=duration,
            )

    def _install_store(
        self,
        resolution: PackageResolution,
        dry_run: bool = False,
        auto_yes: bool = False,
    ) -> ExecutionResult:
        """Install a Snap, Flatpak, or GitHub package through its native backend."""
        package = resolution.package
        source = resolution.source

        backend: SnapBackend | FlatpakBackend | GithubBackend
        if source == "snap":
            backend = SnapBackend()
        elif source == "github":
            backend = GithubBackend()
        else:
            backend = FlatpakBackend()

        if source == "snap":
            command = f"snap install {package}"
        elif source == "github":
            command = f"github_install {package}"
        else:
            command = f"flatpak install -y flathub {package}"

        verification = self.verifier.verify(package, source)
        resolution.trust_tier = verification.tier
        for warning in verification.warnings:
            self.display.warning(warning)

        try:
            self.validator.validate(command)
            if source == "snap":
                self.validator.validate_snap_name(package)
            elif source == "github":
                self.validator.validate_github_repo(package)
            else:
                self.validator.validate_flatpak_id(package)
        except SecurityViolation as e:
            self.display.error(str(e))
            return ExecutionResult(
                success=False,
                package=package,
                command=command,
                output=str(e),
                source=source,
            )

        self.display.show_resolution(
            {
                "package": package,
                "source": source,
                "confidence": resolution.confidence,
                "trust_tier": resolution.trust_tier,
                "version": resolution.version,
                "size": resolution.size or "unknown",
                "notes": resolution.notes or verification.details,
            }
        )

        # CVE Scan
        from sapt.security.vulnerabilities import VulnerabilityScanner

        scanner = VulnerabilityScanner()
        with self.display.spinner(f"Checking OSV CVE database for {package}..."):
            ecosystem = "Debian"
            cve_report = scanner.scan(
                package,
                version=resolution.version,
                ecosystem=ecosystem,
            )
        if not cve_report.ok:
            cve_status = "lookup failed"
            self.display.warning(f"CVE lookup failed: {cve_report.error}")
        elif cve_report.vulnerable:
            cve_status = f"{len(cve_report.vulnerabilities)} CVEs found"
            self.display.warning(
                f"[bold red]⚠️ Found {len(cve_report.vulnerabilities)} "
                f"known vulnerability(ies) for {package}:[/]"
            )
            for vuln in cve_report.vulnerabilities[:3]:
                self.display.warning(f"  - {vuln.id} ({vuln.severity})")
            if len(cve_report.vulnerabilities) > 3:
                self.display.warning(
                    f"  - ... and {len(cve_report.vulnerabilities) - 3} more."
                )
        else:
            cve_status = "no known CVEs"
        self.display.console.print()

        sudo_prefix = "sudo " if source == "snap" else ""
        if dry_run:
            self.display.info(
                "[dim]--dry-run:[/] No changes made. "
                f"Would run: [bold]{sudo_prefix}{command}[/]"
            )
            return ExecutionResult(
                success=True,
                package=package,
                command=f"{sudo_prefix}{command} (dry-run)",
                source=source,
            )

        try:
            if backend.is_installed(package):
                self.display.success(
                    f"[sapt.package]{package}[/] is already installed."
                )
                return ExecutionResult(
                    success=True,
                    package=package,
                    command="(already installed)",
                    source=source,
                )
        except StoreBackendError as e:
            self.display.error(str(e))
            return ExecutionResult(
                success=False,
                package=package,
                command=command,
                output=str(e),
                return_code=1,
                source=source,
            )

        if not auto_yes:
            if not is_interactive():
                message = (
                    "Confirmation required in a non-interactive session."
                    " Use --yes or --dry-run."
                )
                self.display.error(message)
                return ExecutionResult(
                    success=False,
                    package=package,
                    command=command,
                    output=message,
                    source=source,
                )
            confirmed = prompts.confirm_install(
                package=package,
                source=source,
                tier=resolution.trust_tier,
                size=resolution.size or "unknown",
                version=resolution.version or "store latest",
                cve_status=cve_status,
                display=self.display,
            )
            if not confirmed:
                self.display.warning("Installation cancelled.")
                return ExecutionResult(
                    success=False,
                    package=package,
                    command=command,
                    output="Cancelled by user.",
                    source=source,
                )

        start = time.time()
        try:
            with self.display.spinner(f"Installing {package} from {source}..."):
                result = backend.install(package)
            duration = time.time() - start
            self.display.console.print()
            self.display.show_install_summary(
                {
                    "package": package,
                    "source": source,
                    "duration": duration,
                    "run_command": package,
                }
            )
            return ExecutionResult(
                success=True,
                package=package,
                command=f"{sudo_prefix}{command}",
                output=result.stdout,
                return_code=result.returncode,
                duration=duration,
                source=source,
            )
        except StoreBackendError as e:
            duration = time.time() - start
            self.display.console.print()
            self.display.error(f"Installation failed: {e}")
            return ExecutionResult(
                success=False,
                package=package,
                command=f"{sudo_prefix}{command}",
                output=str(e),
                return_code=1,
                duration=duration,
                source=source,
            )

    def remove(
        self,
        package: str,
        purge: bool = False,
        dry_run: bool = False,
        auto_yes: bool = False,
    ) -> ExecutionResult:
        """Remove a package."""
        action = "purge" if purge else "remove"
        command = f"apt {action} -y {package}"

        try:
            self.validator.validate(command)
            self.validator.validate_package_name(package)
        except SecurityViolation as e:
            self.display.error(str(e))
            return ExecutionResult(
                success=False,
                package=package,
                command=command,
                output=str(e),
            )

        # Check if installed
        if not self.apt.is_installed(package):
            self.display.warning(f"[sapt.package]{package}[/] is not installed.")
            return ExecutionResult(
                success=False,
                package=package,
                command=command,
                output="Not installed.",
            )

        # Check reverse dependencies
        rdeps = self.apt.get_reverse_dependencies(package)

        if dry_run:
            self.display.info(
                "[dim]--dry-run:[/] No changes made. "
                f"Would run: [bold]sudo {command}[/]"
            )
            return ExecutionResult(
                success=True,
                package=package,
                command=f"sudo {command} (dry-run)",
            )

        if not auto_yes:
            if not is_interactive():
                message = (
                    "Confirmation required in a non-interactive session."
                    " Use --yes or --dry-run."
                )
                self.display.error(message)
                return ExecutionResult(
                    success=False,
                    package=package,
                    command=command,
                    output=message,
                )
            confirmed = prompts.confirm_remove(
                package=package,
                reverse_deps=rdeps if rdeps else None,
                display=self.display,
            )
            if not confirmed:
                self.display.warning("Removal cancelled.")
                return ExecutionResult(
                    success=False,
                    package=package,
                    command=command,
                    output="Cancelled by user.",
                )

        start = time.time()
        try:
            with self.display.spinner(f"Removing {package}..."):
                if purge:
                    result = self.apt.purge(package)
                else:
                    result = self.apt.remove(package)
            duration = time.time() - start

            self.display.console.print()
            self.display.show_remove_summary(package)

            return ExecutionResult(
                success=True,
                package=package,
                command=f"sudo {command}",
                output=result.stdout,
                return_code=result.returncode,
                duration=duration,
            )

        except AptError as e:
            duration = time.time() - start
            self.display.error(f"Removal failed: {e}")
            return ExecutionResult(
                success=False,
                package=package,
                command=f"sudo {command}",
                output=str(e),
                return_code=1,
                duration=duration,
            )

    def update(self) -> ExecutionResult:
        """Run apt update."""
        start = time.time()
        try:
            with self.display.spinner("Updating package lists..."):
                result = self.apt.update()
            duration = time.time() - start
            self.display.success(f"Package lists updated. ({duration:.1f}s)")
            return ExecutionResult(
                success=True,
                package="",
                command="sudo apt update",
                output=result.stdout,
                duration=duration,
            )
        except AptError as e:
            self.display.error(f"Update failed: {e}")
            return ExecutionResult(
                success=False,
                package="",
                command="sudo apt update",
                output=str(e),
                return_code=1,
            )

    def upgrade(self, auto_yes: bool = False) -> ExecutionResult:
        """Run apt upgrade."""
        if not auto_yes:
            if not is_interactive():
                message = (
                    "Confirmation required in a non-interactive session. Use --yes."
                )
                self.display.error(message)
                return ExecutionResult(
                    success=False,
                    package="",
                    command="sudo apt upgrade",
                    output=message,
                )
            confirmed = prompts.confirm_upgrade([], display=self.display)
            if not confirmed:
                self.display.warning("Upgrade cancelled.")
                return ExecutionResult(
                    success=False,
                    package="",
                    command="sudo apt upgrade",
                    output="Cancelled.",
                )

        start = time.time()
        try:
            with self.display.spinner("Upgrading packages..."):
                result = self.apt.upgrade()
            duration = time.time() - start
            self.display.success(f"System upgraded. ({duration:.1f}s)")
            return ExecutionResult(
                success=True,
                package="",
                command="sudo apt upgrade -y",
                output=result.stdout,
                duration=duration,
            )
        except AptError as e:
            self.display.error(f"Upgrade failed: {e}")
            return ExecutionResult(
                success=False,
                package="",
                command="sudo apt upgrade",
                output=str(e),
                return_code=1,
            )
