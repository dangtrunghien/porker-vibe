from __future__ import annotations

from datetime import datetime
from enum import StrEnum, auto
from pathlib import Path
import re
import traceback
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Static

from vibe.cli.textual_ui.widgets.no_markup_static import NoMarkupStatic
from vibe.collaborative.task_manager import TaskStatus
from vibe.core.planning_models import ItemStatus

if TYPE_CHECKING:
    from vibe.collaborative.vibe_integration import CollaborativeVibeIntegration
    from vibe.core.plan_manager import PlanManager

# Display constants
MAX_TODO_TEXT_LENGTH = 40
MAX_VISIBLE_TODOS = 5


class TodoStatus(StrEnum):
    """Status of a todo item (parsed from markdown)."""

    PENDING = auto()
    IN_PROGRESS = auto()
    COMPLETED = auto()


class TodoWidget(Static):
    """Widget to display the current plan/todos.

    Reads todos directly from `.vibe/plans/todos.md` file.
    Supports both core PlanManager and Collaborative TaskManager.
    """

    def __init__(
        self,
        plan_manager: PlanManager,
        workdir: Path,
        collaborative_integration: CollaborativeVibeIntegration | None = None,
        collapsed: bool = True,
    ) -> None:
        super().__init__()
        self.plan_manager = plan_manager
        self._workdir = workdir
        self._todos_file = workdir / ".vibe" / "plans" / "todos.md"
        self.collaborative_integration = collaborative_integration
        self.collapsed = collapsed
        self.add_class("todo-widget")
        self._last_state: str = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="todo-container"):
            yield NoMarkupStatic("Plan / Todos", id="todo-header")
            self._todo_list = VerticalScroll(id="todo-list")
            yield self._todo_list

    async def on_mount(self) -> None:
        await self.update_todos()

    def _parse_todos_from_file(self) -> list[tuple[str, TodoStatus]]:
        """Parse todos from the markdown file."""
        if not self._todos_file.exists():
            return []

        try:
            content = self._todos_file.read_text(encoding="utf-8")
            lines = content.splitlines()
            todos: list[tuple[str, TodoStatus]] = []

            pattern = re.compile(r"^\s*-\s*\[([\s/xX])\]\s*(.+?)(?:\s*<!--.*-->)?$")

            for line in lines:
                match = pattern.match(line)
                if not match:
                    continue

                status_char = match.group(1).lower()
                content_text = match.group(2).strip()

                if status_char == "x":
                    status = TodoStatus.COMPLETED
                elif status_char == "/":
                    status = TodoStatus.IN_PROGRESS
                else:
                    status = TodoStatus.PENDING

                todos.append((content_text, status))

            return todos
        except Exception:
            return []

    def _get_file_todo_data(self) -> list[tuple[str, TodoStatus]]:
        """Get todo data from markdown file."""
        return self._parse_todos_from_file()

    def _get_plan_todo_data(self) -> list[tuple[str, str, str]]:
        """Get hierarchical plan data: (type, name, status_class)."""
        if not self.plan_manager or not self.plan_manager.current_plan:
            return []

        data = []
        plan = self.plan_manager.current_plan
        for epic in plan.epics:
            data.append(("epic", epic.name, self._get_status_class(epic.status)))
            for task in epic.tasks:
                data.append(("task", task.name, self._get_status_class(task.status)))
                for subtask in task.subtasks:
                    data.append((
                        "subtask",
                        subtask.name,
                        self._get_status_class(subtask.status),
                    ))
        return data

    def _get_collaborative_todo_data(self) -> list[tuple[str, str]]:
        """Get collaborative task data: (description, status_class)."""
        if (
            not self.collaborative_integration
            or not self.collaborative_integration.collaborative_agent
        ):
            return []

        tasks = self.collaborative_integration.collaborative_agent.task_manager.tasks
        return [
            (t.description or "", self._get_status_class(t.status))
            for t in tasks.values()
        ]

    async def update_todos(self) -> None:
        """Update the todo display efficiently."""
        try:
            # 1. Gather all data first (no DOM touches)
            file_todos = self._get_file_todo_data()
            plan_todos = self._get_plan_todo_data()
            collab_todos = self._get_collaborative_todo_data()

            # 2. State check to prevent redundant updates and flashing
            current_state = str((file_todos, plan_todos, collab_todos))
            if current_state == self._last_state:
                return
            self._last_state = current_state

            # 3. Batch the UI update
            def do_update() -> None:
                self._todo_list.remove_children()

                has_content = False

                # Render file todos
                if file_todos:
                    has_content = True
                    for text, status in file_todos:
                        icon = self._get_todo_status_icon(status)
                        status_class = self._get_status_class(status)
                        self._todo_list.mount(
                            NoMarkupStatic(
                                f"{icon} {text}", classes=f"todo-task {status_class}"
                            )
                        )

                # Render plan todos
                if plan_todos:
                    if has_content:
                        self._todo_list.mount(
                            NoMarkupStatic("---", classes="todo-separator")
                        )
                    has_content = True
                    for item_type, name, status_class in plan_todos:
                        # Map type to icon/indent
                        prefix = ""
                        # Re-calculate icon based on status string for plan items
                        icon = "○"
                        if "completed" in status_class:
                            icon = "✓"
                        elif "progress" in status_class:
                            icon = "▶"

                        if item_type == "epic":
                            classes = f"todo-epic {status_class}"
                        elif item_type == "task":
                            prefix = "  "
                            classes = f"todo-task {status_class}"
                        else:  # subtask
                            prefix = "    "
                            classes = f"todo-subtask {status_class}"

                        self._todo_list.mount(
                            NoMarkupStatic(f"{prefix}{icon} {name}", classes=classes)
                        )

                # Render collaborative todos
                if collab_todos:
                    if has_content:
                        self._todo_list.mount(
                            NoMarkupStatic("---", classes="todo-separator")
                        )
                    has_content = True
                    for desc, status_class in collab_todos:
                        self._todo_list.mount(
                            NoMarkupStatic(
                                f"○ {desc}", classes=f"todo-task {status_class}"
                            )
                        )

                if not has_content:
                    self._todo_list.mount(
                        NoMarkupStatic("○ No active tasks", classes="todo-empty")
                    )

            # Textual's App has batch_update, but Static/Widget doesn't directly.
            # However, batch_update is accessible via self.app.
            with self.app.batch_update():
                do_update()

            self.display = True
        except Exception as e:
            # Error logging remains same...
            self._log_error(e)
            raise

    def _log_error(self, e: Exception) -> None:
        error_log_path = Path.home() / ".vibe" / "error.log"
        try:
            error_log_path.parent.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(error_log_path, "a", encoding="utf-8") as f:
                f.write(f"\n{'=' * 80}\n")
                f.write(f"[{timestamp}] Error in TodoWidget.update_todos()\n")
                f.write(traceback.format_exc())
                f.write(f"\n{'=' * 80}\n")
        except Exception:
            pass

    def _get_status_class(self, status: ItemStatus | TodoStatus | TaskStatus) -> str:
        """Get the CSS class for a status."""
        # Convert TaskStatus/ItemStatus to a string if needed
        status_str = str(status).lower()
        if "completed" in status_str:
            return "todo-completed"
        if "in_progress" in status_str or "progress" in status_str:
            return "todo-in-progress"
        return "todo-pending"

    def _get_todo_status_icon(self, status: TodoStatus) -> str:
        match status:
            case TodoStatus.COMPLETED:
                return "✓"
            case TodoStatus.IN_PROGRESS:
                return "▶"
            case TodoStatus.PENDING:
                return "○"
            case _:
                return " "

    def _get_status_icon(self, status: ItemStatus) -> str:
        match status:
            case ItemStatus.COMPLETED:
                return "✓"
            case ItemStatus.IN_PROGRESS:
                return "▶"
            case ItemStatus.FAILED:
                return "✕"
            case ItemStatus.BLOCKED:
                return "!"
            case ItemStatus.SKIPPED:
                return "○"
            case _:
                return " "

    def _get_collab_status_icon(self, status: TaskStatus) -> str:
        match status:
            case TaskStatus.COMPLETED:
                return "✓"
            case TaskStatus.IN_PROGRESS:
                return "▶"
            case TaskStatus.ASSIGNED:
                return "●"
            case TaskStatus.PENDING:
                return "○"
            case _:
                return " "

    async def set_collapsed(self, collapsed: bool) -> None:
        self.collapsed = collapsed
        if collapsed:
            self.add_class("-collapsed")
        else:
            self.remove_class("-collapsed")
        self._todo_list.display = not collapsed
