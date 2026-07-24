"""
sapt.security.vulnerabilities
Optional vulnerability lookups via the OSV.dev API.
"""

from dataclasses import dataclass, field

import requests


@dataclass
class Vulnerability:
    """Compact vulnerability finding."""

    id: str
    summary: str = ""
    severity: str = "unknown"
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
        payload = {"package": {"name": package, "ecosystem": ecosystem}}
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
        for raw in data.get("vulns", []):
            severity = "unknown"
            severities = raw.get("severity") or []
            if severities:
                severity = severities[0].get("score") or severities[0].get("type") or "unknown"
            vulns.append(
                Vulnerability(
                    id=raw.get("id", "unknown"),
                    summary=raw.get("summary", ""),
                    severity=severity,
                    details_url=raw.get("database_specific", {}).get("url", ""),
                )
            )

        return VulnerabilityReport(
            package=package,
            ecosystem=ecosystem,
            version=version,
            vulnerabilities=vulns,
        )
