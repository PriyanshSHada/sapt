"""
sapt.cli
CLI argument parsing and command dispatching.
Uses argparse for zero-dependency argument handling.
"""

import sys
import argparse

from sapt import __version__, __tagline__


def build_parser() -> argparse.ArgumentParser:
    """Build the main argument parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog="sapt",
        description=f"SmartAPT — AI-Powered Secure Package Manager\n{__tagline__}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  sapt install nmap           Install a package (AI-resolved)\n"
            "  sapt install wireshrk       Auto-corrects typos\n"
            "  sapt remove nmap            Remove a package\n"
            "  sapt search 'port scanner'  Natural language search\n"
            "  sapt explain nmap           Learn what a tool does\n"
            "  sapt doctor                 System health check\n"
            "  sapt history                View action history\n"
            "  sapt audit                  Audit log integrity report\n"
            "  sapt completion bash        Print shell completion script\n"
            "  sapt why libssl3            Show reverse dependencies\n"
            "  sapt diff                   Show recorded package changes\n"
            "  sapt config                 Setup wizard\n"
            "\n"
            "Run 'sapt <command> --help' for more info on a command."
        ),
    )

    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"sapt (SmartAPT) {__version__}",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored output",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output local reports as JSON (doctor, history, audit, why, diff, cache)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed debug information",
    )

    # ── Subcommands ──────────────────────────────────────────────
    sub = parser.add_subparsers(dest="command", help="Available commands")

    def add_local_json_flag(command_parser: argparse.ArgumentParser) -> None:
        command_parser.add_argument(
            "--json",
            action="store_true",
            default=argparse.SUPPRESS,
            help=argparse.SUPPRESS,
        )

    # list
    p_list = sub.add_parser("list", help="List packages installed by sapt")
    add_local_json_flag(p_list)
    p_list.add_argument("--source", choices=["apt", "snap", "flatpak", "github"], help="Filter by source")
    p_list.add_argument("--vulnerable", action="store_true", help="List packages with known vulnerabilities")

    # install
    p_install = sub.add_parser("install", help="Install a package")
    p_install.add_argument("package", nargs="+", help="Package name(s) to install")
    p_install.add_argument(
        "--dry-run", action="store_true", help="Preview only, no changes"
    )
    p_install.add_argument(
        "--source",
        choices=["apt", "snap", "flatpak", "github"],
        help="Force install from specific source",
    )
    p_install.add_argument("--version", help="Install this exact APT package version")
    p_install.add_argument(
        "-y", "--yes", action="store_true", help="Skip confirmation prompts"
    )
    p_install.add_argument(
        "--force", action="store_true", help="Override security blocks (like CVSS > 9.0)"
    )

    # remove
    p_remove = sub.add_parser("remove", help="Remove a package")
    p_remove.add_argument("package", help="Package name to remove")
    p_remove.add_argument(
        "--clean", action="store_true", help="Also remove configs and cache (purge)"
    )
    p_remove.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")

    # update
    sub.add_parser("update", help="Update package lists")

    # upgrade
    p_upgrade = sub.add_parser("upgrade", help="Upgrade installed packages")
    p_upgrade.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")

    # search
    p_search = sub.add_parser("search", help="Search for packages (natural language)")
    p_search.add_argument("query", nargs="+", help="Search query")

    # explain
    p_explain = sub.add_parser("explain", help="Explain what a tool does")
    p_explain.add_argument("tool", help="Tool/package name")

    # learn
    p_learn = sub.add_parser("learn", help="Learn how to use a tool")
    p_learn.add_argument("tool", help="Tool/package name")

    # ask (signature feature)
    p_ask = sub.add_parser("ask", help="Describe a goal, get tool recommendations")
    p_ask.add_argument("goal", nargs="+", help="What you want to accomplish")

    # doctor
    p_doctor = sub.add_parser("doctor", help="System health check")
    add_local_json_flag(p_doctor)

    # history
    p_history = sub.add_parser("history", help="View action history")
    add_local_json_flag(p_history)
    p_history.add_argument(
        "-n", "--count", type=int, default=20, help="Number of entries"
    )
    p_history.add_argument(
        "--verify", action="store_true", help="Verify audit log integrity"
    )

    # audit
    p_audit = sub.add_parser("audit", help="Summarize and verify the audit log")
    add_local_json_flag(p_audit)
    p_audit.add_argument(
        "-n", "--count", type=int, default=10, help="Recent entries to include"
    )
    p_audit.add_argument(
        "--entries", action="store_true", help="Include recent entries in the report"
    )
    p_audit.add_argument(
        "--cve", nargs="*", metavar="PACKAGE", help="Check packages against OSV"
    )

    # completion
    p_completion = sub.add_parser("completion", help="Print shell completion script")
    p_completion.add_argument(
        "shell", choices=["bash", "zsh", "fish"], help="Shell to generate for"
    )

    # why
    p_why = sub.add_parser("why", help="Show packages that depend on a package")
    add_local_json_flag(p_why)
    p_why.add_argument("package", help="Installed package to inspect")

    # diff
    p_diff = sub.add_parser("diff", help="Show recent package changes from history")
    add_local_json_flag(p_diff)
    p_diff.add_argument(
        "-n", "--count", type=int, default=20, help="Number of history entries"
    )

    # undo
    p_undo = sub.add_parser("undo", help="Reverse the latest package change")
    p_undo.add_argument(
        "--dry-run", action="store_true", help="Preview only, no changes"
    )
    p_undo.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")

    # agent
    p_agent = sub.add_parser(
        "agent", help="Recommend and install an APT toolkit for a goal"
    )
    p_agent.add_argument("goal", nargs="+", help="The task you want to accomplish")
    p_agent.add_argument(
        "--dry-run", action="store_true", help="Preview only, no changes"
    )
    p_agent.add_argument(
        "-y", "--yes", action="store_true", help="Skip confirmation prompts"
    )

    # cache
    p_cache = sub.add_parser("cache", help="Inspect or clear the AI response cache")
    add_local_json_flag(p_cache)
    cache_group = p_cache.add_mutually_exclusive_group()
    cache_group.add_argument(
        "--stats", action="store_true", help="Show cache statistics (default)"
    )
    cache_group.add_argument(
        "--clear", action="store_true", help="Delete all cached AI responses"
    )

    # alias
    p_alias = sub.add_parser("alias", help="Manage local package aliases")
    add_local_json_flag(p_alias)
    p_alias.add_argument("name", nargs="?", help="Alias to set or inspect")
    p_alias.add_argument(
        "package", nargs="?", help="APT package target when setting an alias"
    )
    p_alias.add_argument("--remove", action="store_true", help="Remove the named alias")
    p_alias.add_argument("--list", action="store_true", help="List all aliases")

    # config
    p_config = sub.add_parser("config", help="Configure SmartAPT")
    add_local_json_flag(p_config)
    config_group = p_config.add_mutually_exclusive_group()
    config_group.add_argument("--show", action="store_true", help="Show current config")
    config_group.add_argument(
        "--set-provider", action="store_true", help="Change AI provider"
    )
    config_group.add_argument(
        "--set-model", action="store_true", help="Change AI model"
    )
    config_group.add_argument("--set-key", action="store_true", help="Update API key")
    config_group.add_argument(
        "--set-endpoint", action="store_true", help="Change endpoint URL"
    )
    config_group.add_argument(
        "--set-budget", type=float, metavar="USD", help="Set monthly AI budget"
    )
    config_group.add_argument(
        "--set-call-cost",
        type=float,
        metavar="USD",
        help="Set estimated cost per AI call",
    )
    config_group.add_argument(
        "--usage", action="store_true", help="Show monthly AI usage"
    )
    config_group.add_argument(
        "--reset", action="store_true", help="Delete config, fresh setup"
    )

    # version
    p_version = sub.add_parser("version", help="Manage package versions")
    add_local_json_flag(p_version)
    p_version.add_argument("package", nargs="?", help="Package to inspect or manage")
    p_version.add_argument("--list", action="store_true", help="List all available versions")
    p_version.add_argument("--show", action="store_true", help="Show current version")
    p_version.add_argument("--pin", metavar="VERSION", help="Pin package to specific version")
    p_version.add_argument("--unpin", action="store_true", help="Unpin package")

    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = build_parser()
    args = parser.parse_args(argv)

    # If no command given, show help
    if args.command is None:
        parser.print_help()
        sys.exit(0)

    return args
