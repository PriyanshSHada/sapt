"""
sapt.commands.completion
Handler for 'sapt completion <shell>'.
"""

import sys


def handle_completion(args, config, display):
    """Print a static shell completion script for the installed CLI."""
    commands = [
        "install",
        "remove",
        "update",
        "upgrade",
        "search",
        "explain",
        "learn",
        "ask",
        "doctor",
        "history",
        "audit",
        "completion",
        "why",
        "diff",
        "list",
        "undo",
        "agent",
        "cache",
        "alias",
        "config",
    ]
    options = {
        "install": "--dry-run --source --version --yes -y",
        "remove": "--clean --yes -y",
        "upgrade": "--yes -y",
        "history": "--count -n --verify",
        "audit": "--count -n --entries --cve --json",
        "completion": "bash zsh fish",
        "diff": "--count -n",
        "list": "--source --vulnerable",
        "undo": "--dry-run --yes -y",
        "agent": "--dry-run --yes -y",
        "cache": "--stats --clear",
        "alias": "--remove --list",
        "config": (
            "--show --set-provider --set-model --set-key"
            " --set-endpoint --set-budget --set-call-cost"
            " --usage --reset --json"
        ),
    }
    script = _completion_script(args.shell, commands, options)
    sys.stdout.write(script)
    if not script.endswith("\n"):
        sys.stdout.write("\n")
    return 0


def _completion_script(shell: str, commands: list[str], options: dict[str, str]) -> str:
    command_words = " ".join(commands)
    if shell == "bash":
        cases = "\n".join(
            f'            {command}) COMPREPLY=( $(compgen -W "{words}" -- "$cur") ) ;;'
            for command, words in sorted(options.items())
        )
        return f"""# sapt bash completion
_sapt_complete()
{{
    local cur command
    COMPREPLY=()
    cur="${{COMP_WORDS[COMP_CWORD]}}"
    command="${{COMP_WORDS[1]}}"

    if [[ $COMP_CWORD -eq 1 ]]; then
        COMPREPLY=( $(compgen -W "{command_words}" -- "$cur") )
        return 0
    fi

    case "$command" in
{cases}
    esac
}}
complete -F _sapt_complete sapt
"""
    if shell == "zsh":
        zsh_commands = " ".join(f"{command}:command" for command in commands)
        zsh_cases = "\n".join(
            f'    {command}) _arguments "*:: :(({words}))" ;;'
            for command, words in sorted(options.items())
        )
        return f"""#compdef sapt
_sapt()
{{
  local -a commands
  commands=({zsh_commands})
  if (( CURRENT == 2 )); then
    _describe -t commands 'sapt command' commands
    return
  fi
  case $words[2] in
{zsh_cases}
  esac
}}
_sapt "$@"
"""
    fish_options = "\n".join(
        f"complete -c sapt -n '__fish_seen_subcommand_from {command}' -f -a '{words}'"
        for command, words in sorted(options.items())
    )
    return f"""# sapt fish completion
complete -c sapt -f -a '{command_words}'
{fish_options}
"""
