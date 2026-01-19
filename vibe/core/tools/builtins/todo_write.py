"""
TodoWrite Tool - Allows agents to manage todos during conversation.

Similar to Claude Code's TodoWrite functionality, this tool enables agents to:
- Create and track tasks
- Mark tasks as pending, in_progress, or completed
- Display progress in the TUI in real-time
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, final

from pydantic import BaseModel, Field

from vibe.core.tools.base import (
    BaseTool,
    BaseToolConfig,
    BaseToolState,
    ToolPermission,
)
from vibe.core.tools.ui import ToolCallDisplay, ToolResultDisplay, ToolUIData

if TYPE_CHECKING:
    from vibe.core.types import ToolCallEvent, ToolResultEvent


class TodoItemInput(BaseModel):
    """A single todo item."""
    content: str = Field(description="The imperative form describing what needs to be done (e.g., 'Run tests', 'Build the project')")
    status: str = Field(description="Task status: 'pending', 'in_progress', or 'completed'")
    activeForm: str = Field(description="The present continuous form shown during execution (e.g., 'Running tests', 'Building the project')")


class TodoWriteArgs(BaseModel):
    """Arguments for the TodoWrite tool."""
    todos: list[TodoItemInput] = Field(
        description="The complete list of todos. Include ALL todos (pending, in_progress, and completed) every time."
    )


class TodoWriteResult(BaseModel):
    """Result from the TodoWrite tool."""
    message: str = Field(description="Confirmation message")
    total: int = Field(description="Total number of todos")
    completed: int = Field(description="Number of completed todos")
    in_progress: int = Field(description="Number of in-progress todos")
    pending: int = Field(description="Number of pending todos")


class TodoWriteConfig(BaseToolConfig):
    """Configuration for the TodoWrite tool."""
    permission: ToolPermission = ToolPermission.ALWAYS


class TodoWriteState(BaseToolState):
    """State for the TodoWrite tool."""
    pass


class TodoWrite(
    BaseTool[TodoWriteArgs, TodoWriteResult, TodoWriteConfig, TodoWriteState],
    ToolUIData[TodoWriteArgs, TodoWriteResult],
):
    """
    Create and manage a structured task list for tracking progress.

    Use this tool to:
    - Track multi-step tasks and their progress
    - Show users what you're working on
    - Demonstrate thoroughness and organization

    Guidelines:
    - Always include the COMPLETE list of todos (don't just send updates)
    - Mark tasks as 'in_progress' BEFORE starting work (limit to ONE at a time)
    - Mark tasks as 'completed' IMMEDIATELY after finishing
    - Use clear, specific task names
    - Provide both 'content' (imperative) and 'activeForm' (continuous) for each task
    """

    description: ClassVar[str] = (
        "Manage a task list to track progress on complex or multi-step work. "
        "Always include the complete list of todos with their current status."
    )

    @final
    async def run(self, args: TodoWriteArgs) -> TodoWriteResult:
        # Get the todo manager from the agent's context
        # This is injected by the agent during initialization
        if not hasattr(self, '_todo_manager'):
            return TodoWriteResult(
                message="Todo manager not initialized",
                total=0,
                completed=0,
                in_progress=0,
                pending=0,
            )

        # Convert todos to dict format for the manager
        todos_data = [
            {
                "content": todo.content,
                "status": todo.status,
                "activeForm": todo.activeForm,
            }
            for todo in args.todos
        ]

        # Update the todo manager
        self._todo_manager.set_todos(todos_data)

        # Get stats
        stats = self._todo_manager.get_stats()

        return TodoWriteResult(
            message="Todos have been modified successfully. Ensure that you continue to use the todo list to track your progress. Please proceed with the current tasks if applicable",
            total=stats["total"],
            completed=stats["completed"],
            in_progress=stats["in_progress"],
            pending=stats["pending"],
        )

    def get_call_display(self, event: ToolCallEvent) -> ToolCallDisplay:
        """Display format for tool call in TUI."""
        args = TodoWriteArgs.model_validate(event.arguments)

        # Count by status
        pending = sum(1 for t in args.todos if t.status == "pending")
        in_progress = sum(1 for t in args.todos if t.status == "in_progress")
        completed = sum(1 for t in args.todos if t.status == "completed")

        detail = f"{len(args.todos)} todos ({completed} completed, {in_progress} in progress, {pending} pending)"

        return ToolCallDisplay(
            title="Update Todo List",
            detail=detail,
        )

    def get_result_display(self, event: ToolResultEvent) -> ToolResultDisplay:
        """Display format for tool result in TUI."""
        if event.error:
            return ToolResultDisplay(detail=f"Error: {event.error}")

        result = TodoWriteResult.model_validate_json(event.result)
        detail = f"Updated: {result.total} todos ({result.completed} completed, {result.in_progress} in progress, {result.pending} pending)"

        return ToolResultDisplay(detail=detail)
