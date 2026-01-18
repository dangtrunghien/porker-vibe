from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Command:
    aliases: frozenset[str]
    description: str
    handler: str
    exits: bool = False


class CommandRegistry:
    def __init__(self, excluded_commands: list[str] | None = None) -> None:
        if excluded_commands is None:
            excluded_commands = []
        self.commands = {
            "help": Command(
                aliases=frozenset(["/help"]),
                description="Show help message",
                handler="_show_help",
            ),
            "config": Command(
                aliases=frozenset(["/config", "/theme", "/model"]),
                description="Edit config settings",
                handler="_show_config",
            ),
            "reload": Command(
                aliases=frozenset(["/reload"]),
                description="Reload configuration from disk",
                handler="_reload_config",
            ),
            "clear": Command(
                aliases=frozenset(["/clear"]),
                description="Clear conversation history",
                handler="_clear_history",
            ),
            "log": Command(
                aliases=frozenset(["/log"]),
                description="Show path to current interaction log file",
                handler="_show_log_path",
            ),
            "compact": Command(
                aliases=frozenset(["/compact"]),
                description="Compact conversation history by summarizing",
                handler="_compact_history",
            ),
            "exit": Command(
                aliases=frozenset(["/exit"]),
                description="Exit the application",
                handler="_exit_app",
                exits=True,
            ),
            "terminal-setup": Command(
                aliases=frozenset(["/terminal-setup"]),
                description="Configure Shift+Enter for newlines",
                handler="_setup_terminal",
            ),
            "status": Command(
                aliases=frozenset(["/status"]),
                description="Display agent statistics",
                handler="_show_status",
            ),
            "autocompactlimit": Command(
                aliases=frozenset(["/autocompactlimit"]),
                description="Set the autocompaction context percentage threshold",
                handler="_set_autocompact_limit",
            ),
            "toggleautocompact": Command(
                aliases=frozenset(["/toggleautocompact"]),
                description="Toggle automatic context compaction on or off",
                handler="_toggle_autocompact",
            ),
            "ralph_start": Command(
                aliases=frozenset(["/ralph start", "/ralph-start"]),
                description="Initiate a new Ralph loop with a development plan",
                handler="_start_ralph_loop",
            ),
            "ralph_status": Command(
                aliases=frozenset(["/ralph status", "/ralph-status"]),
                description="Get the current status of the active Ralph loop",
                handler="_get_ralph_loop_status",
            ),
            "ralph_next": Command(
                aliases=frozenset(["/ralph next", "/ralph-next"]),
                description="Execute the next task in the active Ralph loop",
                handler="_execute_next_ralph_task",
            ),
            "ralph_all": Command(
                aliases=frozenset(["/ralph all", "/ralph-all"]),
                description="Execute all pending tasks in the active Ralph loop",
                handler="_execute_all_ralph_tasks",
            ),
            "ralph_cancel": Command(
                aliases=frozenset(["/ralph cancel", "/ralph-cancel"]),
                description="Cancel the active Ralph loop",
                handler="_cancel_ralph_loop",
            ),
            "plan": Command(
                aliases=frozenset(["/plan", "/generate plan"]),
                description="Generate a development plan for a project and await approval to start a Ralph loop",
                handler="_initiate_planning_session",
            ),
        }

        for command in excluded_commands:
            self.commands.pop(command, None)

        self._alias_map = {}
        for cmd_name, cmd in self.commands.items():
            for alias in cmd.aliases:
                self._alias_map[alias] = cmd_name

    def find_command(self, user_input: str) -> Command | None:
        cmd_name = self._alias_map.get(user_input.lower().strip())
        return self.commands.get(cmd_name) if cmd_name else None

    def get_help_text(self) -> str:
        lines: list[str] = [
            "### Keyboard Shortcuts",
            "",
            "- `Enter` Submit message",
            "- `Ctrl+J` / `Shift+Enter` Insert newline",
            "- `Escape` Interrupt agent or close dialogs",
            "- `Ctrl+C` Quit (or clear input if text present)",
            "- `Ctrl+O` Toggle tool output view",

            "- `Shift+Tab` Toggle auto-approve mode",
            "",
            "### Special Features",
            "",
            "- `!<command>` Execute bash command directly",
            "- `@path/to/file/` Autocompletes file paths",
            "",
            "### Commands",
            "",
        ]

        for cmd in self.commands.values():
            aliases = ", ".join(f"`{alias}`" for alias in sorted(cmd.aliases))
            lines.append(f"- {aliases}: {cmd.description}")
        return "\n".join(lines)