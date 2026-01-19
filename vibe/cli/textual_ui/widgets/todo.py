from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Static

from vibe.cli.textual_ui.widgets.no_markup_static import NoMarkupStatic
from vibe.core.planning_models import ItemStatus
from vibe.collaborative.task_manager import TaskStatus
from vibe.core.todo_manager import TodoStatus

if TYPE_CHECKING:
    from vibe.core.plan_manager import PlanManager
    from vibe.core.todo_manager import TodoManager
    from vibe.collaborative.vibe_integration import CollaborativeVibeIntegration


class TodoWidget(Static):
    """
    Widget to display the current plan/todos.
    Supports both core PlanManager and Collaborative TaskManager.
    """

    def __init__(
        self,
        plan_manager: PlanManager,
        todo_manager: TodoManager,
        collaborative_integration: CollaborativeVibeIntegration | None = None,
        collapsed: bool = True
    ) -> None:
        super().__init__()
        self.plan_manager = plan_manager
        self.todo_manager = todo_manager
        self.collaborative_integration = collaborative_integration
        self.collapsed = collapsed
        self.add_class("todo-widget")

    def compose(self) -> ComposeResult:
        with Vertical(id="todo-container"):
            yield NoMarkupStatic("Plan / Todos", id="todo-header")
            self._todo_list = VerticalScroll(id="todo-list")
            yield self._todo_list

    async def on_mount(self) -> None:
        await self.update_todos()

    async def update_todos(self) -> None:
        has_content = False
        await self._todo_list.remove_children()

        # 1. Check TodoManager (agent-created todos)
        all_todos = self.todo_manager.get_todos_in_order()
        
        # Show first 5 that are NOT completed
        active_todos = [t for t in all_todos if t.status != TodoStatus.COMPLETED]
        
        if active_todos:
            has_content = True
            visible_todos = active_todos[:5]

            for todo in visible_todos:
                icon = self._get_todo_status_icon(todo.status)
                text = todo.active_form if todo.status == TodoStatus.IN_PROGRESS else todo.content
                if len(text) > 40:
                    text = text[:37] + "..."
                
                await self._todo_list.mount(
                    NoMarkupStatic(f"{icon} {text}", classes="todo-task")
                )

            if len(active_todos) > 5:
                await self._todo_list.mount(
                    NoMarkupStatic(f"  ... (+{len(active_todos)-5} more)", classes="todo-more")
                )

        # 2. Check core PlanManager
        if self.plan_manager.current_plan:
            plan = self.plan_manager.current_plan
            # Only show if not fully completed
            if any(epic.status != ItemStatus.COMPLETED for epic in plan.epics):
                if has_content:
                    await self._todo_list.mount(NoMarkupStatic("---", classes="todo-separator"))
                has_content = True
                await self._todo_list.mount(NoMarkupStatic(f"Goal: {plan.goal[:30]}...", classes="todo-goal"))

        # 3. Check Collaborative TaskManager
        if self.collaborative_integration and self.collaborative_integration.collaborative_agent:
            tasks = self.collaborative_integration.collaborative_agent.task_manager.tasks
            active_collab = [t for t in tasks.values() if t.status != TaskStatus.COMPLETED]
            if active_collab:
                if has_content:
                    await self._todo_list.mount(NoMarkupStatic("---", classes="todo-separator"))
                
                has_content = True
                for task in active_collab[:3]: # Limit collab tasks too
                    status_icon = self._get_collab_status_icon(task.status)
                    await self._todo_list.mount(
                        NoMarkupStatic(f"{status_icon} {task.description[:35]}", classes="todo-task")
                    )

        if not has_content:
            await self._todo_list.mount(NoMarkupStatic("○ No active tasks", classes="todo-empty"))

        self.display = True

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
