"""
sapt.__main__
Main entry point — dispatches CLI commands to handlers.
Run with: python -m sapt or just 'sapt' after pip install.
"""

import sys
import logging

from sapt.cli import parse_args
from sapt.ui.display import Display
from sapt.config.manager import ConfigManager
from sapt.config.wizard import run_wizard
from sapt.utils.system import ensure_directories
from sapt.utils.logger import setup_logging


def main():
    """Main entry point for sapt."""
    ensure_directories()

    args = parse_args()
    display = Display(
        no_color=getattr(args, "no_color", False),
        quiet=getattr(args, "json", False),
    )

    # Configure logging (DEBUG if --verbose, else INFO)
    log_level = logging.DEBUG if getattr(args, "verbose", False) else logging.INFO
    logger = setup_logging(level=log_level)
    logger.info(f"SmartAPT starting (verbose: {log_level == logging.DEBUG})")

    try:
        # Import the handler registry (lazy — only loaded after arg parsing)
        from sapt.commands import COMMAND_HANDLERS, handle_config, handle_history

        # Config command doesn't need AI setup
        if args.command == "config":
            return handle_config(args, display)

        # History doesn't need AI either
        if args.command == "history":
            return handle_history(args, display)

        # Only explanatory/generative commands require an AI provider.
        # Install and search can fall back to the local package index, while
        # native APT operations remain usable without any AI setup.
        config_mgr = ConfigManager()
        provider_required_commands = {"explain", "learn", "ask", "agent"}
        if args.command not in provider_required_commands:
            config = {}
            if config_mgr.exists():
                try:
                    config = config_mgr.load()
                except ValueError as e:
                    # Native and offline-capable commands do not depend on a
                    # healthy AI configuration.
                    logger.debug(f"Config load skipped (offline mode): {e}")
        elif not config_mgr.exists():
            display.banner()
            display.info("First time? Let's set up your AI provider.\n")
            config = run_wizard()
            if config is None:
                display.error("Setup cancelled. Run 'sapt config' to try again.")
                logger.info("Setup cancelled by user")
                return 1
            logger.info(f"AI provider configured: {config.get('provider')}")
        else:
            try:
                config = config_mgr.load()
                logger.debug(f"Config loaded for provider: {config.get('provider')}")
            except (ValueError, FileNotFoundError) as e:
                display.error(str(e))
                logger.error(f"Failed to load config: {e}")
                return 1

        # Dispatch to command handler
        handler = COMMAND_HANDLERS.get(args.command)
        if handler:
            logger.info(f"Executing command: {args.command}")
            return handler(args, config, display)
        else:
            display.error(f"Unknown command: {args.command}")
            logger.error(f"Unknown command: {args.command}")
            return 1

    except KeyboardInterrupt:
        display.console.print("\n")
        display.warning("Interrupted by user.")
        logger.info("Interrupted by user")
        return 130
    except Exception as e:
        display.error(f"Unexpected error: {e}")
        logger.exception("Unexpected error")
        return 1


if __name__ == "__main__":
    sys.exit(main() or 0)
