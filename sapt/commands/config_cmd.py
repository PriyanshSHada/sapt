"""
sapt.commands.config_cmd
Handler for 'sapt config'.
"""

from sapt.commands._helpers import emit_json
from sapt.ui.themes import ICONS


def handle_config(args, display):
    """Handle 'sapt config' subcommand."""
    from sapt.config.manager import ConfigManager
    from sapt.config.wizard import run_wizard
    from sapt.utils.constants import PROVIDER_CONFIGS

    config_mgr = ConfigManager()

    if args.show:
        if not config_mgr.exists():
            display.error("No config found. Run 'sapt config' to set up.")
            return 1
        display.banner_mini()
        config = config_mgr.show()
        from rich.table import Table
        from rich import box

        table = Table(
            box=box.ROUNDED,
            border_style="#7C3AED",
            title=f"{ICONS['gear']} Current Configuration",
        )
        table.add_column("Setting", style="bold")
        table.add_column("Value")
        for key, value in config.items():
            if key not in ("api_key_encrypted", "_encrypted", "version"):
                table.add_row(key, str(value))
        display.console.print(table)
        return 0

    if args.reset:
        config_mgr.reset()
        display.success("Config deleted. Run 'sapt config' for fresh setup.")
        return 0

    if args.usage:
        from sapt.ai.usage import UsageTracker
        from rich.table import Table
        from rich import box

        summary = UsageTracker().monthly_summary()
        if args.json:
            emit_json(summary)
            return 0
        table = Table(
            box=box.ROUNDED,
            border_style="#7C3AED",
            title=f"{ICONS['chart']} AI Usage ({summary['month']})",
        )
        table.add_column("Metric", style="bold")
        table.add_column("Value")
        table.add_row("Calls", str(summary["calls"]))
        table.add_row("Successes", str(summary["successes"]))
        table.add_row("Failures", str(summary["failures"]))
        table.add_row("Estimated spend", f"${summary['estimated_spend_usd']:.4f}")
        display.console.print(table)
        return 0

    if args.set_budget is not None or args.set_call_cost is not None:
        if not config_mgr.exists():
            display.error("No config found. Run 'sapt config' to set up first.")
            return 1
        if args.set_budget is not None:
            if args.set_budget < 0:
                display.error("Budget must be zero or greater.")
                return 1
            config_mgr.set("monthly_budget_usd", f"{args.set_budget:.6f}")
            display.success(f"Monthly AI budget set to ${args.set_budget:.4f}.")
        else:
            if args.set_call_cost < 0:
                display.error("Estimated call cost must be zero or greater.")
                return 1
            config_mgr.set("estimated_cost_per_call_usd", f"{args.set_call_cost:.6f}")
            display.success(f"Estimated AI call cost set to ${args.set_call_cost:.6f}.")
        return 0

    if args.set_key:
        import questionary

        new_key = questionary.password("Enter new API key:").ask()
        if new_key:
            config_mgr.set("api_key", new_key.strip())
            display.success("API key updated.")
        return 0

    if args.set_provider:
        # A provider change also needs its model, endpoint, and key, so the
        # setup wizard is the safest way to collect a complete configuration.
        run_wizard()
        return 0

    if args.set_model or args.set_endpoint:
        if not config_mgr.exists():
            display.error("No config found. Run 'sapt config' to set up first.")
            return 1

        import questionary

        config = config_mgr.load()
        if args.set_model:
            provider = config.get("provider", "custom")
            models = PROVIDER_CONFIGS.get(provider, {}).get("models", [])
            if models:
                value = questionary.select(
                    "Select model:",
                    choices=models,
                    default=config.get("model"),
                ).ask()
            else:
                value = questionary.text(
                    "Enter model name:",
                    default=config.get("model", ""),
                ).ask()
            key, label = "model", "Model"
        else:
            value = questionary.text(
                "Enter API endpoint URL:",
                default=config.get("endpoint", ""),
            ).ask()
            key, label = "endpoint", "Endpoint"

        if value:
            config_mgr.set(key, value.strip())
            display.success(f"{label} updated.")
        return 0

    # Default: run full wizard
    run_wizard()
    return 0
