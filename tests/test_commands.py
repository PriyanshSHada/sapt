import unittest
from unittest.mock import patch, MagicMock
from types import SimpleNamespace
import io
import json

from sapt.commands.alias import handle_alias
from sapt.commands.ask import handle_ask
from sapt.commands.diff import handle_diff
from sapt.commands.doctor import handle_doctor
from sapt.commands.explain import handle_explain
from sapt.commands.history import handle_history
from sapt.commands.learn import handle_learn
from sapt.commands.list_cmd import handle_list
from sapt.commands.remove import handle_remove
from sapt.commands.search import handle_search
from sapt.commands.update import handle_update
from sapt.commands.upgrade import handle_upgrade
from sapt.commands.config_cmd import handle_config

class CommandTests(unittest.TestCase):
    def setUp(self):
        self.config = {"provider": "openai"}
        self.display = MagicMock()
        self.display.console = MagicMock()

    @patch("sapt.config.aliases.AliasManager")
    def test_alias_list(self, mock_am):
        mock_am.return_value.get_all.return_value = {"ls": "exa"}
        args = SimpleNamespace(list=True, remove=False, name=None, package=None, json=False)
        self.assertEqual(handle_alias(args, self.config, self.display), 0)

    @patch("sapt.config.aliases.AliasManager")
    def test_alias_set(self, mock_am):
        args = SimpleNamespace(list=False, remove=False, name="ls", package="exa", json=False)
        self.assertEqual(handle_alias(args, self.config, self.display), 0)
        mock_am.return_value.set.assert_called_with("ls", "exa")

    @patch("sapt.config.aliases.AliasManager")
    def test_alias_remove(self, mock_am):
        args = SimpleNamespace(list=False, remove=True, name="ls", package=None, json=False)
        mock_am.return_value.remove.return_value = True
        self.assertEqual(handle_alias(args, self.config, self.display), 0)

    @patch("sapt.ai.providers.get_provider")
    def test_ask(self, mock_gp):
        mock_gp.return_value.call.return_value = {"tools": [{"package": "nmap", "why": "network"}]}
        args = SimpleNamespace(goal=["network", "scan"])
        self.assertEqual(handle_ask(args, self.config, self.display), 0)

    @patch("sapt.security.audit.AuditLogger")
    def test_diff(self, mock_audit):
        mock_audit.return_value.get_all.return_value = [{"action": "install", "package": "nmap", "success": True, "source": "apt"}]
        args = SimpleNamespace(count=10, json=False)
        self.assertEqual(handle_diff(args, self.config, self.display), 0)

    @patch("sapt.config.manager.ConfigManager")
    def test_doctor(self, mock_cm):
        args = SimpleNamespace(json=False)
        self.assertEqual(handle_doctor(args, self.config, self.display), 0)

    @patch("sapt.ai.providers.get_provider")
    def test_explain(self, mock_gp):
        mock_gp.return_value.call.return_value = {"summary": "explain text"}
        args = SimpleNamespace(tool="nmap")
        self.assertEqual(handle_explain(args, self.config, self.display), 0)

    @patch("sapt.security.audit.AuditLogger")
    def test_history(self, mock_audit):
        mock_audit.return_value.get_history.return_value = [{"action": "install"}]
        args = SimpleNamespace(count=10, verify=False, json=False)
        self.assertEqual(handle_history(args, self.display), 0)

    @patch("sapt.ai.providers.get_provider")
    def test_learn(self, mock_gp):
        mock_gp.return_value.call.return_value = {"commands": [{"command": "nmap -sV", "description": "scan"}]}
        args = SimpleNamespace(tool="nmap")
        self.assertEqual(handle_learn(args, self.config, self.display), 0)

    @patch("sapt.security.audit.AuditLogger")
    def test_list(self, mock_audit):
        mock_audit.return_value.get_all.return_value = [
            {"action": "install", "package": "nmap", "success": True, "version": "1.0", "source": "apt", "timestamp": "2026-08-03"}
        ]
        args = SimpleNamespace(source=None, vulnerable=False, json=False)
        self.assertEqual(handle_list(args, self.config, self.display), 0)

    @patch("sapt.execution.executor.Executor")
    @patch("sapt.security.audit.AuditLogger")
    def test_remove(self, mock_audit, mock_exec):
        mock_exec.return_value.remove.return_value = SimpleNamespace(success=True, command="sudo apt remove nmap")
        args = SimpleNamespace(package="nmap", yes=True, clean=False)
        self.assertEqual(handle_remove(args, self.config, self.display), 0)
        mock_exec.return_value.remove.assert_called_with(package="nmap", auto_yes=True, purge=False)

    @patch("sapt.ai.resolver.get_provider")
    def test_search(self, mock_gp):
        mock_gp.return_value.call.return_value = {"packages": [{"package": "nmap", "description": "network", "confidence": 1.0}]}
        args = SimpleNamespace(query=["network"])
        self.assertEqual(handle_search(args, self.config, self.display), 0)

    @patch("sapt.execution.executor.Executor")
    @patch("sapt.security.audit.AuditLogger")
    def test_update(self, mock_audit, mock_exec):
        mock_exec.return_value.update.return_value = SimpleNamespace(success=True, command="apt update")
        args = SimpleNamespace()
        self.assertEqual(handle_update(args, self.config, self.display), 0)

    @patch("sapt.execution.executor.Executor")
    @patch("sapt.security.audit.AuditLogger")
    def test_upgrade(self, mock_audit, mock_exec):
        mock_exec.return_value.upgrade.return_value = SimpleNamespace(success=True, command="apt upgrade -y")
        args = SimpleNamespace(yes=True)
        self.assertEqual(handle_upgrade(args, self.config, self.display), 0)

    @patch("sapt.config.manager.ConfigManager")
    def test_config_show(self, mock_cm):
        mock_cm.return_value.read.return_value = self.config
        args = SimpleNamespace(show=True, set_provider=False, set_model=False, set_key=False, set_endpoint=False, set_budget=None, set_call_cost=None, usage=False, reset=False, json=False)
        self.assertEqual(handle_config(args, self.display), 0)

if __name__ == "__main__":
    unittest.main()
