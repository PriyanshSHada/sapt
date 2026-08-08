"""
sapt.security.vulnerabilities
Optional vulnerability lookups via the OSV.dev API.
"""

from dataclasses import dataclass, field

import requests

SEVERITY_THRESHOLDS = {
    "block": 9.0,    # CVSS 9+ = hard block (override with --force)
    "warn": 7.0,     # CVSS 7-8.9 = yellow warning
    "info": 4.0,     # CVSS 4-6.9 = info only
}

@dataclass
class Vulnerability:
    """Compact vulnerability finding."""

    id: str
    summary: str = ""
    severity: str = "unknown"
    cvss_score: float = 0.0
    details_url: str = ""


@dataclass
class VulnerabilityReport:
    """Vulnerability lookup result for one package."""

    package: str
    ecosystem: str = "Debian"
    version: str = ""
    ok: bool = True
    error: str = ""
    vulnerabilities: list[Vulnerability] = field(default_factory=list)

    @property
    def vulnerable(self) -> bool:
        return bool(self.vulnerabilities)

    @property
    def max_cvss(self) -> float:
        return max((v.cvss_score for v in self.vulnerabilities), default=0.0)

    def to_dict(self) -> dict:
        return {
            "package": self.package,
            "ecosystem": self.ecosystem,
            "version": self.version,
            "ok": self.ok,
            "error": self.error,
            "vulnerable": self.vulnerable,
            "vulnerabilities": [
                {
                    "id": vuln.id,
                    "summary": vuln.summary,
                    "severity": vuln.severity,
                    "cvss_score": vuln.cvss_score,
                    "details_url": vuln.details_url,
                }
                for vuln in self.vulnerabilities
            ],
        }


class VulnerabilityScanner:
    """Query OSV for known package vulnerabilities."""

    endpoint = "https://api.osv.dev/v1/query"

    def __init__(self, timeout: int = 8):
        self.timeout = timeout

    def scan(
        self,
        package: str,
        version: str = "",
        ecosystem: str = "Debian",
    ) -> VulnerabilityReport:
        payload: dict = {
            "package": {"name": package, "ecosystem": ecosystem}
        }
        if version:
            payload["version"] = version

        try:
            response = requests.post(
                self.endpoint,
                json=payload,
                timeout=self.timeout,
            )
            if response.status_code != 200:
                return VulnerabilityReport(
                    package=package,
                    ecosystem=ecosystem,
                    version=version,
                    ok=False,
                    error=f"OSV API returned HTTP {response.status_code}",
                )
            data = response.json()
        except (requests.ConnectionError, requests.Timeout) as error:
            return VulnerabilityReport(
                package=package,
                ecosystem=ecosystem,
                version=version,
                ok=False,
                error=str(error),
            )
        except ValueError as error:
            return VulnerabilityReport(
                package=package,
                ecosystem=ecosystem,
                version=version,
                ok=False,
                error=f"Invalid OSV response: {error}",
            )

        vulns = []
        has_cvss = False
        cvss = None
        try:
            import cvss
            has_cvss = True
        except ImportError:
            pass

        for raw in data.get("vulns", []):
            severity = "unknown"
            cvss_score = 0.0
            severities = raw.get("severity") or []
            if severities:
                for sev in severities:
                    val = sev.get("score") or sev.get("type") or ""
                    if val.startswith("CVSS:"):
                        try:
                            if has_cvss:
                                cvss_score = cvss.CVSS3(val).scores()[0]
                            severity = val
                        except Exception:
                            pass
                if severity == "unknown":
                    severity = (
                        severities[0].get("score") or severities[0].get("type") or "unknown"
                    )

            vulns.append(
                Vulnerability(
                    id=raw.get("id", "unknown"),
                    summary=raw.get("summary", ""),
                    severity=severity,
                    cvss_score=cvss_score,
                    details_url=raw.get("database_specific", {}).get("url", ""),
                )
            )

        return VulnerabilityReport(
            package=package,
            ecosystem=ecosystem,
            version=version,
            vulnerabilities=vulns,
        )
