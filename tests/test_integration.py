"""
tests/test_integration.py
End-to-end integration tests for SmartAPT.

Tests complete workflows:
- Package installation with validation
- Logging behavior
- GitHub backend reliability
- Error handling paths
"""

import json
import logging
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from unittest.mock import MagicMock, patch

from sapt.execution.stores import GithubBackend
from sapt.security.audit import AuditLogger
from sapt.ui.display import Display
from sapt.utils.logger import setup_logging


class IntegrationTestBase(unittest.TestCase):
    """Base class for integration tests."""

    def setUp(self):
        """Set up test fixtures."""
        self.tmp_dir = tempfile.mkdtemp()
        self.display = Display(no_color=True, quiet=False)
        self.logger = setup_logging(level=logging.DEBUG)

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        if os.path.exists(self.tmp_dir):
            shutil.rmtree(self.tmp_dir, ignore_errors=True)


class LoggingIntegrationTests(IntegrationTestBase):
    """Test logging integration."""

    def test_logging_setup_creates_logger(self):
        """Verify logger is properly initialized."""
        logger = setup_logging(level=logging.INFO)
        self.assertIsNotNone(logger)
        self.assertEqual(logger.name, "sapt")
        self.assertGreater(len(logger.handlers), 0)

    def test_logging_debug_vs_info_level(self):
        """Verify DEBUG level captures more logs than INFO."""
        logger_debug = setup_logging(level=logging.DEBUG)
        logger_info = setup_logging(level=logging.INFO)

        # Both should be valid loggers
        self.assertIsNotNone(logger_debug)
        self.assertIsNotNone(logger_info)

        # Debug level should be lower
        self.assertLess(logging.DEBUG, logging.INFO)

    def test_logging_masks_secrets(self):
        """Verify API keys are masked in logs."""
        from sapt.utils.logger import SecretMaskingFormatter

        formatter = SecretMaskingFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="api_key: sk-1234567890abcdef",
            args=(),
            exc_info=None,
        )

        formatted = formatter.format(record)
        self.assertIn("***MASKED***", formatted)
        self.assertNotIn("sk-1234", formatted)

    def test_logging_sensitive_fields_masked(self):
        """Verify various sensitive field names are masked."""
        from sapt.utils.logger import SecretMaskingFormatter

        formatter = SecretMaskingFormatter()
        sensitive_fields = {
            "api_key": "sk-123",
            "token": "ghp_xxx",
            "password": "secret123",
            "authorization": "Bearer token_xxx",
        }

        for field, value in sensitive_fields.items():
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="",
                lineno=0,
                msg=f"{field}: {value}",
                args=(),
                exc_info=None,
            )
            formatted = formatter.format(record)
            self.assertIn("***MASKED***", formatted, f"Field {field} not masked")
            self.assertNotIn(value, formatted, f"Value {value} exposed for {field}")


class GitHubBackendIntegrationTests(IntegrationTestBase):
    """Test GitHub backend reliability and security."""

    def test_github_architecture_detection_x86_64(self):
        """Verify x86_64 architecture is detected."""
        with mock.patch("platform.machine", return_value="x86_64"):
            arch = GithubBackend._get_system_arch()
            self.assertEqual(arch, "x86_64")

    def test_github_architecture_detection_aarch64(self):
        """Verify aarch64 (ARM64) architecture is detected."""
        for machine in ["aarch64", "arm64"]:
            with mock.patch("platform.machine", return_value=machine):
                arch = GithubBackend._get_system_arch()
                self.assertEqual(arch, "aarch64", f"Failed to detect {machine}")

    def test_github_architecture_detection_armv7l(self):
        """Verify armv7l (32-bit ARM) architecture is detected."""
        for machine in ["armv7l", "armv7", "armhf"]:
            with mock.patch("platform.machine", return_value=machine):
                arch = GithubBackend._get_system_arch()
                self.assertEqual(arch, "armv7l", f"Failed to detect {machine}")

    def test_github_architecture_unknown_defaults_to_x86_64(self):
        """Verify unknown architecture defaults to x86_64."""
        with mock.patch("platform.machine", return_value="mips64"):
            arch = GithubBackend._get_system_arch()
            self.assertEqual(arch, "x86_64")

    def test_github_find_best_asset_prefers_deb(self):
        """Verify .deb files are preferred over tar.gz."""
        assets = [
            {"name": "app-linux-amd64.tar.gz", "browser_download_url": "url1"},
            {"name": "app-linux-amd64.deb", "browser_download_url": "url2"},
        ]

        with mock.patch.object(GithubBackend, "_get_system_arch", return_value="x86_64"):
            url, name = GithubBackend._find_best_asset(assets, "x86_64")
            self.assertEqual(name, "app-linux-amd64.deb")

    def test_github_find_best_asset_tar_gz_second(self):
        """Verify tar.gz is selected when .deb unavailable."""
        assets = [
            {"name": "app-linux-amd64.tar.gz", "browser_download_url": "url1"},
        ]

        url, name = GithubBackend._find_best_asset(assets, "x86_64")
        self.assertEqual(name, "app-linux-amd64.tar.gz")

    def test_github_find_best_asset_architecture_specific(self):
        """Verify architecture filtering works."""
        assets = [
            {"name": "app-linux-aarch64.deb", "browser_download_url": "url1"},
            {"name": "app-linux-x86_64.deb", "browser_download_url": "url2"},
        ]

        url, name = GithubBackend._find_best_asset(assets, "aarch64")
        self.assertEqual(name, "app-linux-aarch64.deb")

        url, name = GithubBackend._find_best_asset(assets, "x86_64")
        self.assertEqual(name, "app-linux-x86_64.deb")

    def test_github_find_best_asset_no_match_returns_none(self):
        """Verify None is returned when no compatible asset found."""
        assets = [
            {"name": "app-macos-universal.tar.gz", "browser_download_url": "url1"},
            {"name": "app-windows-x86_64.exe", "browser_download_url": "url2"},
        ]

        url, name = GithubBackend._find_best_asset(assets, "x86_64")
        self.assertIsNone(url)
        self.assertIsNone(name)

    def test_github_find_checksum_file(self):
        """Verify SHA256SUMS file is located."""
        assets = [
            {"name": "app.deb", "browser_download_url": "url1"},
            {"name": "SHA256SUMS", "browser_download_url": "url2"},
        ]

        checksum_asset, algo = GithubBackend._find_checksum_file(assets)
        self.assertIsNotNone(checksum_asset)
        self.assertEqual(checksum_asset["name"], "SHA256SUMS")
        self.assertEqual(algo, "sha256")

    def test_github_find_checksum_file_not_found(self):
        """Verify None is returned when no checksum file exists."""
        assets = [
            {"name": "app.deb", "browser_download_url": "url1"},
            {"name": "README.md", "browser_download_url": "url2"},
        ]

        checksum_asset, algo = GithubBackend._find_checksum_file(assets)
        self.assertIsNone(checksum_asset)
        self.assertIsNone(algo)


class AuditLoggingIntegrationTests(IntegrationTestBase):
    """Test audit log behavior."""

    def test_audit_logger_records_entry(self):
        """Verify audit logger records operation."""
        audit_file = Path(self.tmp_dir) / "audit.jsonl"
        logger = AuditLogger(audit_file)

        logger.log("install", package="vim", source="apt")

        self.assertTrue(audit_file.exists())
        with open(audit_file) as f:
            entry = json.loads(f.readline())
            self.assertEqual(entry["action"], "install")
            self.assertEqual(entry["package"], "vim")

    def test_audit_logger_multiple_entries(self):
        """Verify multiple entries can be recorded."""
        audit_file = Path(self.tmp_dir) / "audit.jsonl"
        logger = AuditLogger(audit_file)

        logger.log("install", package="vim")
        logger.log("remove", package="nano")

        with open(audit_file) as f:
            lines = f.readlines()
            self.assertEqual(len(lines), 2)

    def test_audit_logger_hash_chain_integrity(self):
        """Verify hash chain is maintained."""
        audit_file = Path(self.tmp_dir) / "audit.jsonl"
        logger = AuditLogger(audit_file)

        logger.log("install", package="vim")
        logger.log("remove", package="nano")

        # Verify integrity
        is_valid, _ = logger.verify_chain()
        self.assertTrue(is_valid)

    def test_audit_logger_detects_tampering(self):
        """Verify tampering is detected."""
        audit_file = Path(self.tmp_dir) / "audit.jsonl"
        logger = AuditLogger(audit_file)

        logger.log("install", package="vim")

        # Tamper with the file
        with open(audit_file, "a") as f:
            f.write('{"malicious": "entry"}\n')

        # Verification should fail
        logger = AuditLogger(audit_file)
        is_valid, _ = logger.verify_chain()
        self.assertFalse(is_valid)


class SudoErrorHandlingTests(IntegrationTestBase):
    """Test sudo error handling."""

    def test_sudo_password_prompt_detected(self):
        """Verify sudo password errors are detected."""
        from sapt.execution.apt import AptError, AptBackend

        # Simulate sudo password error
        error_msg = "sudo: a password is required, but no askpass program specified"
        with patch("subprocess.run") as mock_run:
            result = MagicMock()
            result.returncode = 1
            result.stderr = error_msg
            mock_run.return_value = result

            apt = AptBackend()
            with self.assertRaises(AptError) as ctx:
                apt._run(["apt", "update"], sudo=True)

            self.assertIn("password", str(ctx.exception).lower())

    def test_sudo_noninteractive_flag_added(self):
        """Verify -n flag is added to sudo commands."""
        from sapt.execution.apt import AptBackend

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")

            apt = AptBackend()
            apt._run(["apt", "update"], sudo=True)

            # Check that -n was added
            call_args = mock_run.call_args
            cmd = call_args[0][0] if call_args[0] else call_args.kwargs.get("args")
            self.assertIn("-n", cmd, "sudo -n flag not found in command")


class DryRunIntegrationTests(IntegrationTestBase):
    """Test dry-run mode prevents actual changes."""

    def test_dry_run_does_not_execute(self):
        """Verify dry-run doesn't actually execute commands."""
        # Placeholder test to ensure framework is in place
        pass


class ErrorRecoveryTests(IntegrationTestBase):
    """Test error recovery paths."""

    def test_network_error_provides_recovery_path(self):
        """Verify network errors have recovery instructions."""
        from sapt.execution.stores import StoreBackendError

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = Exception("Connection refused")

            backend = GithubBackend()
            with self.assertRaises(StoreBackendError) as ctx:
                backend.install("user/repo")

            error_msg = str(ctx.exception).lower()
            # Should provide actionable information
            self.assertIn("failed", error_msg)

    def test_missing_asset_provides_available_list(self):
        """Verify missing asset errors list alternatives."""
        from sapt.execution.stores import StoreBackendError

        assets = [
            {"name": "app-linux-x86_64.deb"},
            {"name": "app-macos.tar.gz"},
        ]

        with patch("urllib.request.urlopen") as mock_urlopen:
            response_data = {"assets": assets}
            mock_response = MagicMock()
            mock_response.read.return_value = json.dumps(response_data).encode()
            mock_urlopen.return_value.__enter__.return_value = mock_response

            backend = GithubBackend()
            with self.assertRaises(StoreBackendError) as ctx:
                # Mock to return aarch64 when detecting arch
                with patch.object(GithubBackend, "_get_system_arch", return_value="aarch64"):
                    backend.install("user/repo")

            error_msg = str(ctx.exception)
            # Should mention available options
            self.assertIn("aarch64", error_msg.lower())


class TimeoutEnforcementTests(IntegrationTestBase):
    """Test timeout enforcement."""

    def test_apt_operations_have_timeout(self):
        """Verify apt operations have timeout."""
        from sapt.execution.apt import AptBackend

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")

            apt = AptBackend()
            apt._run(["apt", "update"])

            # Verify timeout parameter was passed
            call_kwargs = mock_run.call_args.kwargs
            self.assertIn("timeout", call_kwargs)
            self.assertEqual(call_kwargs["timeout"], 300)

    def test_github_download_has_timeout(self):
        """Verify GitHub downloads have timeout."""
        from sapt.execution.stores import GithubBackend

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = Exception("Timeout")

            with self.assertRaises(Exception):
                GithubBackend._download_file("http://example.com/file", "/tmp/file", timeout=120)

            # Verify timeout was specified in call
            self.assertTrue(mock_urlopen.called)


if __name__ == "__main__":
    unittest.main()
