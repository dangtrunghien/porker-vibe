from __future__ import annotations

from enum import StrEnum
from typing import ClassVar, Self, final

import aiofiles
from pydantic import BaseModel, Field, model_validator

from vibe.core.tools.base import (
    BaseTool,
    BaseToolConfig,
    BaseToolState,
    ToolError,
    ToolPermission,
)
from vibe.core.tools.ui import ToolCallDisplay, ToolResultDisplay, ToolUIData
from vibe.core.types import ToolCallEvent, ToolResultEvent


class TodoStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class TodoWriteArgs(BaseModel):
    content: str | None = Field(
        default=None,
        description="Full content of the todos.md file in markdown format. Provide EITHER this OR task/status.",
    )
    task: str | None = Field(
        default=None,
        description="The task description to update. Required if content is None.",
    )
    status: TodoStatus | None = Field(
        default=None,
        description="The new status for the task. Required if content is None.",
    )

    @model_validator(mode="after")
    def check_args(self) -> Self:
        if self.content is None and (self.task is None or self.status is None):
            raise ValueError(
                "Must provide either 'content' OR both 'task' and 'status'"
            )
        return self


class TodoWriteResult(BaseModel):
    path: str
    bytes_written: int
    message: str


class TodoWriteConfig(BaseToolConfig):
    permission: ToolPermission = ToolPermission.ALWAYS


class TodoWriteState(BaseToolState):
    pass


class TodoWrite(
    BaseTool[TodoWriteArgs, TodoWriteResult, TodoWriteConfig, TodoWriteState],
    ToolUIData[TodoWriteArgs, TodoWriteResult],
):
    """Maintain a persistent list of tasks in ./.vibe/plans/todos.md.

    This tool is the primary way to track progress in the UI.
    ALWAYS mark a task as 'in_progress' BEFORE starting work on it and 'completed' IMMEDIATELY after finishing.
    Use GFM task list syntax:
    - [ ] pending
    - [/] in_progress
    - [x] completed
    """

    description: ClassVar[str] = (
        "Create or update the project's todo list at ./.vibe/plans/todos.md."
    )

    @classmethod
    def get_call_display(cls, event: ToolCallEvent) -> ToolCallDisplay:
        if not isinstance(event.args, TodoWriteArgs):
            return ToolCallDisplay(summary="Invalid arguments")

        if event.args.content:
            return ToolCallDisplay(
                summary="Updating todo list", content=event.args.content
            )
        else:
            return ToolCallDisplay(
                summary=f"Updating todo: {event.args.task} -> {event.args.status}",
                content=f"Task: {event.args.task}\nStatus: {event.args.status}",
            )

    @classmethod
    def get_result_display(cls, event: ToolResultEvent) -> ToolResultDisplay:
        if isinstance(event.result, TodoWriteResult):
            return ToolResultDisplay(success=True, message=event.result.message)
        return ToolResultDisplay(success=True, message="Todo list updated")

    @classmethod
    def get_status_text(cls) -> str:
        return "Updating todos"

    @final
    async def run(self, args: TodoWriteArgs) -> TodoWriteResult:
        todo_path = self.config.effective_workdir / ".vibe" / "plans" / "todos.md"

        try:
            todo_path.parent.mkdir(parents=True, exist_ok=True)

            if args.content is not None:
                # Full rewrite mode
                final_content = args.content
            else:
                # Partial update mode
                if not todo_path.exists():
                    raise ToolError(f"Todo file not found at {todo_path}")

                async with aiofiles.open(todo_path, encoding="utf-8") as f:
                    current_content = await f.read()

                if args.task and args.status:
                    final_content = self._update_task_status(
                        current_content, args.task, args.status
                    )
                else:
                    # Should be caught by validator, but safe fallback
                    final_content = current_content

            content_bytes = len(final_content.encode("utf-8"))

            async with aiofiles.open(todo_path, mode="w", encoding="utf-8") as f:
                await f.write(final_content)

            # Plan sync hook: update dev/PLAN.md checkboxes based on todo status
            self._sync_to_plan_md(final_content)

            return TodoWriteResult(
                path=str(todo_path),
                bytes_written=content_bytes,
                message=f"Updated todos.md ({content_bytes} bytes)",
            )
        except Exception as e:
            raise ToolError(f"Error writing todo file {todo_path}: {e}") from e

    def _update_task_status(
        self, content: str, task_name: str, status: TodoStatus
    ) -> str:
        """Update status of a specific task in content."""
        import re

        lines = content.splitlines()
        updated_lines = []
        task_found = False

        # Status char map
        status_char = " "
        if status == TodoStatus.IN_PROGRESS:
            status_char = "/"
        elif status == TodoStatus.COMPLETED:
            status_char = "x"

        # Regex to match todo items
        # Matches: - [ ] Task Name
        pattern = re.compile(r"^(\s*-\s*\[)([\sxyXY/])(\]\s*)(.+?)(?:\s*<!--.*-->)?$")

        normalized_target = task_name.strip().lower().replace("*", "")

        for line in lines:
            match = pattern.match(line)
            if match and not task_found:
                prefix_start = match.group(1)
                _current_status = match.group(2)
                prefix_end = match.group(3)
                item_text = match.group(4)

                # Check for match
                normalized_item = item_text.strip().lower().replace("*", "")

                # Simple containment check for robustness
                if (
                    normalized_target in normalized_item
                    or normalized_item in normalized_target
                ):
                    # Found it! Update status
                    updated_lines.append(
                        f"{prefix_start}{status_char}{prefix_end}{item_text}"
                    )
                    task_found = True
                    continue

            updated_lines.append(line)

        return "\n".join(updated_lines) + "\n"

    def _sync_to_plan_md(self, todos_content: str) -> None:
        """Sync completed todos to dev/PLAN.md checkboxes.

        When a todo is marked [x] in todos.md, find matching items in PLAN.md
        and update their checkboxes.
        """
        import re

        plan_path = self.config.effective_workdir / "dev" / "PLAN.md"
        if not plan_path.exists():
            return

        try:
            # Parse todos to find completed items
            todo_pattern = re.compile(
                r"^\s*-\s*\[([xX/\s])\]\s*\*{0,2}(.+?)\*{0,2}\s*$"
            )
            completed_items: set[str] = set()
            in_progress_items: set[str] = set()

            for line in todos_content.splitlines():
                match = todo_pattern.match(line)
                if match:
                    status_char = match.group(1).lower()
                    item_name = match.group(2).strip()
                    # Normalize: remove markdown bold markers
                    item_name = item_name.strip("*").strip()

                    if status_char == "x":
                        completed_items.add(item_name.lower())
                    elif status_char == "/":
                        in_progress_items.add(item_name.lower())

            if not completed_items and not in_progress_items:
                return

            # Read and update PLAN.md
            plan_content = plan_path.read_text(encoding="utf-8")
            plan_lines = plan_content.splitlines()
            updated_lines: list[str] = []
            plan_pattern = re.compile(
                r"^(\s*-\s*)\[([xX\s])\]\s*\*{0,2}(.+?)\*{0,2}\s*$"
            )

            for line in plan_lines:
                match = plan_pattern.match(line)
                if match:
                    prefix = match.group(1)
                    _current_status = match.group(2)  # Unused but kept for clarity
                    item_name = match.group(3).strip().strip("*").strip()

                    if item_name.lower() in completed_items:
                        # Mark as completed
                        updated_lines.append(f"{prefix}[x] **{item_name}**")
                    else:
                        updated_lines.append(line)
                else:
                    updated_lines.append(line)

            # Write back if changed
            new_content = "\n".join(updated_lines)
            if new_content != plan_content:
                plan_path.write_text(new_content + "\n", encoding="utf-8")

        except Exception:
            # Plan sync should not fail the main todo write
            pass
