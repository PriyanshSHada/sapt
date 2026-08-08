import unittest
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from sapt.ai.sanitizer import InvalidAIResponseError, validate_ai_response
from sapt.ai.resolver import PackageResolver
from sapt.ai.usage import UsageTracker
from sapt.config.aliases import AliasError, AliasManager
from sapt.execution.executor import Executor
from sapt.execution.validator import CommandValidator, SecurityViolation
from sapt.ai.resolver import PackageResolution
from sapt.security.audit import AuditLogger
from sapt.security.vulnerabilities import VulnerabilityScanner
from sapt.security.verification import PackageVerifier
from sapt.cli import parse_args


class SanitizerTests(unittest.TestCase):
    def test_rejects_unsafe_ai_package_name(self):
        with self.assertRaises(InvalidAIResponseError):
            validate_ai_response(
                '{"package":"curl;rm -rf /","source":"apt","confidence":1}'
            )


class ValidatorTests(unittest.TestCase):
    def test_allows_exact_apt_operation(self):
        self.assertTrue(CommandValidator().validate("apt install -y nmap"))

    def test_rejects_lookalike_allowlist_prefix(self):
        with self.assertRaises(SecurityViolation):
            CommandValidator().validate("apt install-malicious nmap")

    def test_allows_safe_apt_version(self):
        self.assertTrue(CommandValidator().validate_version("1:2.0.0~beta-1"))

    def test_rejects_unsafe_apt_version(self):
        with self.assertRaises(SecurityViolation):
            CommandValidator().validate_version("1.0;rm")

    def test_validates_snap_and_flatpak_names(self):
        validator = CommandValidator()

        self.assertTrue(validator.validate_snap_name("code-insiders"))
        self.assertTrue(validator.validate_flatpak_id("com.visualstudio.code"))
        with self.assertRaises(SecurityViolation):
            validator.validate_snap_name("BadSnap")
        with self.assertRaises(SecurityViolation):
            validator.validate_flatpak_id("firefox")


class VerificationTests(unittest.TestCase):
    def test_apt_verification_has_official_trust_tier(self):
        result = PackageVerifier().verify("nmap", "apt")

        self.assertEqual(result.tier, 1)
        self.assertTrue(result.signed)
        self.assertTrue(result.checksum_ok)


class AliasTests(unittest.TestCase):
    def test_aliases_persist_and_resolve(self):
        with TemporaryDirectory() as directory:
            manager = AliasManager(Path(directory) / "aliases.json")
            manager.set("burp", "burpsuite")

            self.assertEqual(manager.resolve("burp"), "burpsuite")
            self.assertTrue(manager.remove("burp"))
            self.assertIsNone(manager.resolve("burp"))

    def test_alias_rejects_unsafe_package_target(self):
        with TemporaryDirectory() as directory:
            manager = AliasManager(Path(directory) / "aliases.json")
            with self.assertRaises(AliasError):
                manager.set("bad", "curl;rm")


class ExecutorSourceTests(unittest.TestCase):
    @patch("sapt.execution.executor.AptBackend")
    def test_does_not_send_non_apt_source_to_apt(self, apt_backend):
        display = MagicMock()
        executor = Executor(display=display)
        result = executor.install(
            PackageResolution(package="tool", source="unknown", confidence=1),
            auto_yes=True,
        )

        self.assertFalse(result.success)
        self.assertIn("not supported", result.output)
        apt_backend.return_value.is_installed.assert_not_called()

    @patch("sapt.execution.executor.SnapBackend")
    @patch("sapt.execution.executor.AptBackend")
    def test_snap_dry_run_does_not_require_backend(self, apt_backend, snap_backend):
        display = MagicMock()
        executor = Executor(display=display)

        result = executor.install(
            PackageResolution(package="postman", source="snap", confidence=1),
            dry_run=True,
        )

        self.assertTrue(result.success)
        self.assertIn("snap install postman", result.command)
        snap_backend.return_value.is_installed.assert_not_called()
        apt_backend.return_value.is_installed.assert_not_called()

    @patch("sapt.execution.executor.FlatpakBackend")
    @patch("sapt.execution.executor.AptBackend")
    def test_flatpak_install_routes_to_flatpak_backend(self, apt_backend, flatpak_backend):
        display = MagicMock()
        backend = flatpak_backend.return_value
        backend.is_installed.return_value = False
        backend.install.return_value = SimpleNamespace(stdout="ok", returncode=0)
        executor = Executor(display=display)

        result = executor.install(
            PackageResolution(package="org.mozilla.firefox", source="flatpak", confidence=1),
            auto_yes=True,
        )

        self.assertTrue(result.success)
        backend.install.assert_called_once_with("org.mozilla.firefox")
        apt_backend.return_value.install.assert_not_called()

    @patch("sapt.execution.executor.is_interactive", return_value=False)
    @patch("sapt.execution.executor.AptBackend")
    def test_install_requires_yes_when_non_interactive(self, apt_backend, _interactive):
        display = MagicMock()
        apt = apt_backend.return_value
        apt.is_installed.return_value = False
        apt.get_size.return_value = "1 MB"
        apt.get_available_version.return_value = "1.0"
        executor = Executor(display=display)

        result = executor.install(
            PackageResolution(package="nmap", source="apt", confidence=1),
        )

        self.assertFalse(result.success)
        self.assertIn("non-interactive", result.output)
        apt.install.assert_not_called()

    @patch("sapt.execution.executor.AptBackend")
    def test_install_passes_requested_version_to_apt(self, apt_backend):
        display = MagicMock()
        apt = apt_backend.return_value
        apt.is_installed.return_value = False
        apt.get_size.return_value = "1 MB"
        apt.get_available_version.return_value = "2.0"
        apt.install.return_value = SimpleNamespace(stdout="", returncode=0)
        executor = Executor(display=display)

        result = executor.install(
            PackageResolution(
                package="nmap", source="apt", confidence=1,
                requested_version="2.0",
            ),
            auto_yes=True,
        )

        self.assertTrue(result.success)
        apt.install.assert_called_once_with("nmap=2.0")


class ResolverTests(unittest.TestCase):
    def test_empty_config_uses_fuzzy_matching_without_provider(self):
        cache = MagicMock()
        cache.get.return_value = None
        fuzzy = MagicMock()
        fuzzy.match.return_value = [("nmap", 100)]
        resolver = PackageResolver({}, cache=cache, fuzzy=fuzzy)

        result = resolver.resolve("nmap")

        self.assertTrue(result.from_fuzzy)
        self.assertEqual(result.package, "nmap")
        cache.get.assert_called_once_with("install", "nmap")

    def test_invalid_ai_mapping_falls_back_to_fuzzy_match(self):
        cache = MagicMock()
        cache.get.return_value = None
        fuzzy = MagicMock()
        fuzzy.match.return_value = [("nmap", 95)]
        resolver = PackageResolver({}, cache=cache, fuzzy=fuzzy)
        resolver._provider = MagicMock()
        resolver._provider.call.return_value = {
            "package": "nmap", "source": "not-a-source", "confidence": 1,
        }

        result = resolver.resolve("nmap")

        self.assertTrue(result.from_fuzzy)
        self.assertEqual(result.package, "nmap")
        cache.set.assert_not_called()

    def test_budget_limit_skips_provider_call(self):
        cache = MagicMock()
        cache.get.return_value = None
        fuzzy = MagicMock()
        fuzzy.match.return_value = []
        usage = MagicMock()
        usage.check_budget.return_value = SimpleNamespace(
            allowed=False,
            message="budget exceeded",
        )
        resolver = PackageResolver(
            {
                "provider": "openai",
                "model": "test",
                "monthly_budget_usd": "1.00",
                "estimated_cost_per_call_usd": "0.50",
            },
            cache=cache,
            fuzzy=fuzzy,
            usage=usage,
        )
        resolver._provider = MagicMock()

        result = resolver.resolve("nmap")

        self.assertTrue(result.from_fuzzy)
        self.assertIn("budget", result.notes)
        resolver._provider.call.assert_not_called()


class UsageTests(unittest.TestCase):
    def test_usage_tracker_records_monthly_spend_and_budget(self):
        with TemporaryDirectory() as directory:
            tracker = UsageTracker(Path(directory) / "usage.db")
            tracker.record("openai", "model", "install", "nmap", True, 0.25)
            tracker.record("openai", "model", "search", "scanner", False, 0.25)

            summary = tracker.monthly_summary()
            decision = tracker.check_budget(0.40, 0.25)

        self.assertEqual(summary["calls"], 2)
        self.assertEqual(summary["failures"], 1)
        self.assertEqual(summary["estimated_spend_usd"], 0.5)
        self.assertFalse(decision.allowed)


class VulnerabilityTests(unittest.TestCase):
    @patch("sapt.security.vulnerabilities.requests.post")
    def test_osv_vulnerability_scan_parses_findings(self, post):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "vulns": [
                {
                    "id": "CVE-2026-0001",
                    "summary": "example vuln",
                    "severity": [{"type": "CVSS_V3", "score": "7.5"}],
                }
            ]
        }
        post.return_value = response

        report = VulnerabilityScanner().scan("openssl")

        self.assertTrue(report.vulnerable)
        self.assertEqual(report.vulnerabilities[0].id, "CVE-2026-0001")


class AuditTests(unittest.TestCase):
    def test_verify_rejects_malformed_audit_line(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "audit.log"
            audit = AuditLogger(path)
            audit.log(action="install", package="nmap")
            with path.open("a") as log:
                log.write("this is not json\\n")

            valid, message = audit.verify_chain()

        self.assertFalse(valid)
        self.assertIn("malformed", message)


class MainDispatchTests(unittest.TestCase):
    @patch("sapt.__main__.ConfigManager")
    @patch("sapt.__main__.Display")
    @patch("sapt.__main__.parse_args")
    def test_doctor_does_not_require_ai_configuration(
        self, parse_args, display_cls, config_manager_cls
    ):
        from sapt.commands import COMMAND_HANDLERS
        from sapt.__main__ import main

        parse_args.return_value = SimpleNamespace(command="doctor", no_color=False)
        config_manager_cls.return_value.exists.return_value = False
        handler = MagicMock(return_value=0)

        with patch.dict(COMMAND_HANDLERS, {"doctor": handler}):
            self.assertEqual(main(), 0)
        handler.assert_called_once()


class LocalCommandTests(unittest.TestCase):
    def test_parser_accepts_why_and_diff(self):
        self.assertEqual(parse_args(["why", "libssl3"]).package, "libssl3")
        self.assertEqual(parse_args(["diff", "--count", "5"]).count, 5)
        self.assertTrue(parse_args(["undo", "--dry-run"]).dry_run)
        self.assertEqual(parse_args(["agent", "inspect", "traffic"]).goal, ["inspect", "traffic"])
        self.assertTrue(parse_args(["cache", "--clear"]).clear)
        self.assertTrue(parse_args(["audit", "--entries"]).entries)
        self.assertTrue(parse_args(["audit", "--json"]).json)
        self.assertEqual(parse_args(["audit", "--cve", "openssl"]).cve, ["openssl"])
        self.assertEqual(parse_args(["completion", "bash"]).shell, "bash")
        self.assertEqual(parse_args(["config", "--set-budget", "5"]).set_budget, 5)

    @patch("sapt.execution.apt.AptBackend")
    def test_why_reports_reverse_dependencies(self, apt_backend):
        from sapt.commands.why import handle_why

        apt = apt_backend.return_value
        apt.is_installed.return_value = True
        apt.get_version.return_value = "3.0"
        apt.get_reverse_dependencies.return_value = ["curl", "wget"]
        display = MagicMock()

        result = handle_why(SimpleNamespace(package="libssl3", json=False), {}, display)

        self.assertEqual(result, 0)
        apt.get_reverse_dependencies.assert_called_once_with("libssl3")

    @patch("sapt.execution.apt.AptBackend")
    def test_why_json_is_machine_readable(self, apt_backend):
        from sapt.commands.why import handle_why

        apt = apt_backend.return_value
        apt.is_installed.return_value = True
        apt.get_version.return_value = "3.0"
        apt.get_reverse_dependencies.return_value = ["curl"]
        output = io.StringIO()

        with patch("sys.stdout", output):
            result = handle_why(
                SimpleNamespace(package="libssl3", json=True), {}, MagicMock(),
            )

        self.assertEqual(result, 0)
        self.assertEqual(json.loads(output.getvalue())["reverse_dependencies"], ["curl"])

    @patch("sapt.execution.executor.Executor")
    @patch("sapt.commands.undo.AuditLogger")
    def test_undo_reverses_latest_install(self, audit_logger, executor_cls):
        from sapt.commands.undo import handle_undo

        audit = audit_logger.return_value
        audit.get_all.return_value = [
            {"id": "a1", "action": "install", "package": "nmap", "success": True},
        ]
        executor_cls.return_value.remove.return_value = SimpleNamespace(
            success=True, command="sudo apt remove -y nmap",
        )

        result = handle_undo(
            SimpleNamespace(dry_run=False, yes=True), {}, MagicMock(),
        )

        self.assertEqual(result, 0)
        executor_cls.return_value.remove.assert_called_once_with(
            "nmap", dry_run=False, auto_yes=True,
        )
        audit.log.assert_called_once()

    @patch("sapt.execution.executor.Executor")
    @patch("sapt.commands.agent.AuditLogger")
    @patch("sapt.ai.providers.get_provider")
    def test_agent_only_installs_valid_apt_package_names(
        self, get_provider, audit_logger, executor_cls
    ):
        from sapt.commands.agent import handle_agent

        get_provider.return_value.call.return_value = {
            "tools": [
                {"package": "nmap", "why": "Network discovery"},
                {"package": "curl; rm -rf /", "why": "Unsafe"},
            ]
        }
        executor_cls.return_value.install.return_value = SimpleNamespace(
            success=True, command="sudo apt install -y nmap",
        )

        result = handle_agent(
            SimpleNamespace(goal=["inspect", "network"], dry_run=True, yes=True),
            {"provider": "openai"}, MagicMock(),
        )

        self.assertEqual(result, 0)
        executor_cls.return_value.install.assert_called_once()
        audit_logger.return_value.log.assert_not_called()

    @patch("sapt.ai.cache.ResponseCache")
    def test_cache_clear_reports_deleted_entries(self, cache_cls):
        from sapt.commands.cache_cmd import handle_cache

        cache_cls.return_value.clear.return_value = 3
        result = handle_cache(
            SimpleNamespace(clear=True, json=False), {}, MagicMock(),
        )

        self.assertEqual(result, 0)
        cache_cls.return_value.clear.assert_called_once()

    @patch("sapt.config.aliases.AliasManager")
    @patch("sapt.execution.executor.Executor")
    @patch("sapt.commands.install.AuditLogger")
    def test_install_with_explicit_snap_source_bypasses_apt_resolution(
        self, audit_logger, executor_cls, alias_manager
    ):
        from sapt.commands.install import handle_install

        alias_manager.return_value.resolve.return_value = None
        executor_cls.return_value.install.return_value = SimpleNamespace(success=True)

        result = handle_install(
            SimpleNamespace(
                package=["postman"], source="snap", version=None,
                dry_run=True, yes=True, force=False,
            ),
            {},
            MagicMock(),
        )

        self.assertEqual(result, 0)
        resolution = executor_cls.return_value.install.call_args.args[0]
        self.assertEqual(resolution.package, "postman")
        self.assertEqual(resolution.source, "snap")
        audit_logger.return_value.log.assert_not_called()

    @patch("sapt.commands.audit.AuditLogger")
    def test_audit_json_reports_summary(self, audit_logger):
        from sapt.commands.audit import handle_audit

        audit = audit_logger.return_value
        audit.verify_chain.return_value = (True, "ok")
        audit.get_all.return_value = [
            {"action": "install", "source": "apt", "success": True},
            {"action": "install", "source": "apt", "success": False},
            {"action": "remove", "source": "apt", "success": True},
        ]
        audit.get_history.return_value = [{"action": "remove"}]
        output = io.StringIO()

        with patch("sys.stdout", output):
            result = handle_audit(
                SimpleNamespace(json=True, entries=True, count=1), {}, MagicMock(),
            )

        payload = json.loads(output.getvalue())
        self.assertEqual(result, 0)
        self.assertEqual(payload["total_entries"], 3)
        self.assertEqual(payload["actions"]["install"], 2)
        self.assertEqual(payload["failures"], 1)
        self.assertEqual(payload["entries"], [{"action": "remove"}])

    @patch("sapt.commands.audit.AuditLogger")
    @patch("sapt.security.vulnerabilities.VulnerabilityScanner")
    def test_audit_cve_json_includes_vulnerability_report(self, scanner_cls, audit_logger):
        from sapt.commands.audit import handle_audit

        audit = audit_logger.return_value
        audit.verify_chain.return_value = (True, "ok")
        audit.get_all.return_value = []
        scanner_cls.return_value.scan.return_value.to_dict.return_value = {
            "package": "openssl",
            "vulnerable": False,
        }
        output = io.StringIO()

        with patch("sys.stdout", output):
            result = handle_audit(
                SimpleNamespace(json=True, entries=False, count=1, cve=["openssl"]),
                {}, MagicMock(),
            )

        payload = json.loads(output.getvalue())
        self.assertEqual(result, 0)
        self.assertEqual(payload["vulnerabilities"][0]["package"], "openssl")

    def test_completion_prints_shell_script(self):
        from sapt.commands.completion import handle_completion

        output = io.StringIO()
        with patch("sys.stdout", output):
            result = handle_completion(
                SimpleNamespace(shell="bash"), {}, MagicMock(),
            )

        self.assertEqual(result, 0)
        self.assertIn("complete -F _sapt_complete sapt", output.getvalue())


if __name__ == "__main__":
    unittest.main()
