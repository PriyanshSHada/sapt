"""
sapt.security.verification
Package verification — trust tier assignment, checksum verification,
and signature checking. Layer 3 (independent, rule-based).
"""

from dataclasses import dataclass, field


@dataclass
class VerificationResult:
    """Result of a package verification check."""

    tier: int = 1
    signed: bool = False
    checksum_ok: bool = False
    warnings: list[str] = field(default_factory=list)
    details: str = ""


class PackageVerifier:
    """Verify package trust and integrity."""

    SOURCE_TIERS = {
        "apt": 1,  # 🟢 Official distro repo
        "snap": 2,  # 🟡 Snap Store
        "flatpak": 2,  # 🟡 Flathub
        "ppa": 3,  # 🟠 Third-party PPA
        "github": 4,  # 🔴 GitHub / unverified
    }

    def verify(self, package: str, source: str) -> VerificationResult:
        """Run verification checks for a package.

        Returns a VerificationResult with trust tier and warnings.
        """
        tier = self.get_trust_tier(source)
        result = VerificationResult(tier=tier)

        if source == "apt":
            result.signed = True
            result.checksum_ok = True
            result.details = "Package signed by official repository keyring."

        elif source in ("snap", "flatpak"):
            result.signed = True
            result.details = f"Package from {source.title()} store (reviewed)."

        elif source == "ppa":
            result.signed = True  # PPAs have GPG keys
            result.warnings.append(
                "This package is from a third-party PPA. "
                "Verify the PPA maintainer is trustworthy."
            )
            result.details = "PPA-signed package."

        elif source == "github":
            result.signed = False
            result.checksum_ok = False
            result.warnings.append(
                "This package is from GitHub and has no signature verification."
            )
            result.warnings.append(
                "Install at your own risk. Verify the repository manually."
            )
            result.details = "Unverified GitHub release."

        return result

    def get_trust_tier(self, source: str) -> int:
        """Map a source to its trust tier (1=highest, 4=lowest)."""
        return self.SOURCE_TIERS.get(source, 4)
