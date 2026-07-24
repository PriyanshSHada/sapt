"""
sapt.config.wizard
First-run interactive setup wizard using questionary for
arrow-key navigation menus (Cline-style UX).
"""

import questionary
from questionary import Style

from sapt.ui.display import Display
from sapt.ui.themes import ICONS
from sapt.config.manager import ConfigManager
from sapt.utils.constants import PROVIDER_CONFIGS


# ── Wizard Prompt Style ──────────────────────────────────────────
WIZARD_STYLE = Style([
    ("qmark", "fg:#7C3AED bold"),
    ("question", "fg:white bold"),
    ("answer", "fg:#06B6D4 bold"),
    ("pointer", "fg:#7C3AED bold"),
    ("highlighted", "fg:#7C3AED bold"),
    ("selected", "fg:#06B6D4"),
    ("separator", "fg:#6B7280"),
    ("instruction", "fg:#6B7280"),
    ("text", "fg:white"),
    ("disabled", "fg:#6B7280 italic"),
])


class SetupWizard:
    """Interactive first-run configuration wizard."""

    def __init__(self):
        self.display = Display()
        self.config_manager = ConfigManager()

    def run(self) -> dict | None:
        """Run the full setup wizard flow.

        Returns the saved config dict, or None if user cancelled.
        """
        self.display.banner()
        self.display.console.print(
            f"  {ICONS['gear']} Welcome to [bold #7C3AED]SmartAPT[/]! "
            f"Let's set up your AI provider.\n"
        )
        self.display.console.print(
            f"  [dim]This is a one-time setup. You can change it anytime "
            f"with [bold]sapt config[/].[/]\n"
        )

        # Step 1: Select provider
        provider_key = self._select_provider()
        if provider_key is None:
            return None

        # Step 2: Get provider-specific config
        config = self._configure_provider(provider_key)
        if config is None:
            return None

        # Step 3: Test connection
        test_now = questionary.confirm(
            f"{ICONS['bolt']} Test connection now?",
            default=True,
            style=WIZARD_STYLE,
        ).ask()

        if test_now is None:  # Ctrl+C
            return None

        if test_now:
            self.display.console.print()
            with self.display.spinner("Testing connection..."):
                success, message = self.config_manager.test_connection(config)

            if success:
                self.display.success(message)
            else:
                self.display.error(message)
                retry = questionary.confirm(
                    "Save config anyway?",
                    default=False,
                    style=WIZARD_STYLE,
                ).ask()
                if not retry:
                    return None

        # Step 4: Save
        self.config_manager.save(config)
        self.display.console.print()
        self.display.success(
            f"Config saved to [dim]{self.config_manager.exists() and '~/.config/sapt/config.json'}[/]"
        )
        self.display.console.print()
        self.display.info(
            "You're all set! Try: [bold]sapt install nmap[/]"
        )
        self.display.console.print()

        return config

    # ── Provider Selection ───────────────────────────────────────

    def _select_provider(self) -> str | None:
        """Let the user pick an AI provider."""
        choices = []
        for key, cfg in PROVIDER_CONFIGS.items():
            choices.append(questionary.Choice(title=cfg["name"], value=key))

        result = questionary.select(
            "Select AI provider:",
            choices=choices,
            style=WIZARD_STYLE,
            instruction="(arrow keys to navigate)",
        ).ask()

        return result

    # ── Provider Configuration ───────────────────────────────────

    def _configure_provider(self, provider_key: str) -> dict | None:
        """Get model, API key, and endpoint for the selected provider."""
        provider_cfg = PROVIDER_CONFIGS[provider_key]
        config = {
            "provider": provider_key,
            "format": provider_cfg["format"],
        }

        if provider_key == "custom":
            return self._configure_custom(config)

        # Known provider — select model from list
        model = questionary.select(
            "Select model:",
            choices=provider_cfg["models"],
            style=WIZARD_STYLE,
        ).ask()
        if model is None:
            return None
        config["model"] = model

        # API key
        api_key = questionary.password(
            f"Enter your {provider_cfg['name'].split('(')[0].strip()} API key:",
            style=WIZARD_STYLE,
        ).ask()
        if not api_key:
            self.display.error("API key is required.")
            return None
        config["api_key"] = api_key.strip()

        # Endpoint is hardcoded for known providers
        config["endpoint"] = provider_cfg["endpoint"]

        return config

    def _configure_custom(self, config: dict) -> dict | None:
        """Configure a custom/third-party AI provider."""
        self.display.console.print()
        self.display.info(
            "Custom providers include: Fireworks, Together AI, Groq, "
            "OpenRouter, Ollama, LM Studio, etc."
        )
        self.display.console.print()

        # Endpoint
        endpoint = questionary.text(
            "Enter API endpoint URL:",
            style=WIZARD_STYLE,
            validate=lambda x: True if x.startswith(("http://", "https://")) else "Must start with http:// or https://",
        ).ask()
        if not endpoint:
            return None
        config["endpoint"] = endpoint.strip()

        # Model name
        model = questionary.text(
            "Enter model name:",
            style=WIZARD_STYLE,
            validate=lambda x: True if len(x.strip()) > 0 else "Model name is required",
        ).ask()
        if not model:
            return None
        config["model"] = model.strip()

        # API key (optional for local LLMs)
        is_local = "localhost" in endpoint or "127.0.0.1" in endpoint
        if is_local:
            self.display.info("Local endpoint detected — API key is optional.")

        api_key = questionary.password(
            "Enter API key (leave blank for local LLMs):",
            style=WIZARD_STYLE,
        ).ask()
        config["api_key"] = (api_key or "").strip() or "local"

        # API format
        api_format = questionary.select(
            "This endpoint follows:",
            choices=[
                questionary.Choice("OpenAI-compatible format", value="openai"),
                questionary.Choice("Anthropic-compatible format", value="anthropic"),
            ],
            style=WIZARD_STYLE,
        ).ask()
        if api_format is None:
            return None
        config["format"] = api_format

        return config


def run_wizard() -> dict | None:
    """Convenience function to run the setup wizard."""
    wizard = SetupWizard()
    return wizard.run()
