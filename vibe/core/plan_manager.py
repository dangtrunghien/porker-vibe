from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional, Type, TypeVar, Union
from uuid import UUID

from vibe.core.planning_models import AgentPlan, Epic, ItemStatus, PlanItem, Subtask, Task

T = TypeVar("T", bound=PlanItem)

class PlanManager:
    """
    Manages the AgentPlan, including creation, loading, saving, and manipulation of plan items.
    """

    def __init__(self, project_path: Path):
        self.project_path = project_path
        self._plan_file_path = self._get_plan_file_path()
        self._agent_plan: Optional[AgentPlan] = None
        self.load_plan() # Attempt to load an existing plan on initialization

    def _get_plan_file_path(self) -> Path:
        """Determines the path where the plan JSON will be stored."""
        vibe_path = self.project_path / ".vibe"
        plans_dir = vibe_path / "plans"
        plans_dir.mkdir(parents=True, exist_ok=True)
        return plans_dir / "agent_plan.json"

    def create_new_plan(self, goal: str) -> AgentPlan:
        """Creates a new AgentPlan and saves it."""
        self._agent_plan = AgentPlan(goal=goal)
        self.save_plan()
        return self._agent_plan

    def load_plan(self) -> Optional[AgentPlan]:
        """Loads an existing AgentPlan from file."""
        if not self._plan_file_path.exists():
            self._agent_plan = None
            return None
        try:
            with self._plan_file_path.open("r", encoding="utf-8") as f:
                plan_data = json.load(f)
            self._agent_plan = AgentPlan.model_validate(plan_data)
            return self._agent_plan
        except (json.JSONDecodeError, FileNotFoundError, IOError) as e:
            self._agent_plan = None
            return None

    def save_plan(self) -> None:
        """Saves the current AgentPlan to file."""
        if self._agent_plan:
            self._agent_plan.last_updated = time.time()
            with self._plan_file_path.open("w", encoding="utf-8") as f:
                json.dump(self._agent_plan.model_dump(mode="json"), f, indent=4)

    @property
    def current_plan(self) -> Optional[AgentPlan]:
        return self._agent_plan

    def _find_item_recursive(self, item_id: UUID, items: list[PlanItem]) -> Optional[PlanItem]:
        """Helper to recursively find an item by ID within a list of PlanItems."""
        for item in items:
            if item.id == item_id:
                return item
            if isinstance(item, Epic):
                found = self._find_item_recursive(item_id, item.tasks)
                if found: return found
            if isinstance(item, Task):
                found = self._find_item_recursive(item_id, item.subtasks)
                if found: return found
        return None

    def get_item_by_id(self, item_id: UUID) -> Optional[PlanItem]:
        """Finds any plan item (Epic, Task, or Subtask) by its ID."""
        if not self._agent_plan:
            return None
        return self._find_item_recursive(item_id, self._agent_plan.epics)

    def update_item_status(self, item_id: UUID, new_status: ItemStatus) -> bool:
        """Updates the status of a plan item and its updated_at timestamp."""
        item = self.get_item_by_id(item_id)
        if item:
            item.status = new_status
            item.updated_at = time.time()
            self.save_plan()
            # Optionally, update parent status if all children are complete
            self._update_parent_status(item_id)
            return True
        return False

    def _update_parent_status(self, child_id: UUID) -> None:
        """Checks if a parent item can be marked as completed based on its children's status."""
        if not self._agent_plan:
            return

        # Find the parent of the child_id
        parent_item: Optional[PlanItem] = None
        for epic in self._agent_plan.epics:
            if child_id in [t.id for t in epic.tasks]:
                parent_item = epic
                break
            for task in epic.tasks:
                if child_id in [s.id for s in task.subtasks]:
                    parent_item = task
                    break
            if parent_item: break

        if parent_item:
            children_are_completed = False
            if isinstance(parent_item, Epic):
                children_are_completed = all(task.status == ItemStatus.COMPLETED for task in parent_item.tasks)
            elif isinstance(parent_item, Task):
                children_are_completed = all(subtask.status == ItemStatus.COMPLETED for subtask in parent_item.subtasks)

            if children_are_completed and parent_item.status != ItemStatus.COMPLETED:
                parent_item.status = ItemStatus.COMPLETED
                parent_item.updated_at = time.time()
                self.save_plan()
                # Recursively check if this completion affects its parent
                self._update_parent_status(parent_item.id)

    def get_next_actionable_item(self) -> Optional[Union[Task, Subtask]]:
        """
        Finds the next actionable item (Task or Subtask) that is PENDING
        and has all its dependencies COMPLETED. Prioritizes subtasks, then tasks.
        """
        if not self._agent_plan:
            return None

        # A cache for dependency status to avoid repeated lookups
        dependency_status_cache = {}

        def is_dependency_completed(dep_id: UUID) -> bool:
            if dep_id not in dependency_status_cache:
                dep_item = self.get_item_by_id(dep_id)
                dependency_status_cache[dep_id] = (dep_item is not None and dep_item.status == ItemStatus.COMPLETED)
            return dependency_status_cache[dep_id]

        for epic in self._agent_plan.epics:
            if epic.status != ItemStatus.PENDING and epic.status != ItemStatus.IN_PROGRESS:
                continue # Skip epics that are not pending or in progress

            for task in epic.tasks:
                if task.status != ItemStatus.PENDING and task.status != ItemStatus.IN_PROGRESS:
                    continue # Skip tasks that are not pending or in progress

                # Check subtasks first
                for subtask in task.subtasks:
                    if subtask.status == ItemStatus.PENDING:
                        if all(is_dependency_completed(dep) for dep in subtask.dependencies):
                            return subtask

                # If no actionable subtask, check the task itself if it has no subtasks
                # or if it has subtasks but they are all completed/skipped/failed.
                if task.status == ItemStatus.PENDING:
                    # If task has subtasks, it's only actionable if all subtasks are non-pending/in_progress
                    if task.subtasks:
                        all_subtasks_handled = all(s.status not in [ItemStatus.PENDING, ItemStatus.IN_PROGRESS] for s in task.subtasks)
                        if all_subtasks_handled and all(is_dependency_completed(dep) for dep in task.dependencies):
                            return task
                    else: # Task has no subtasks, check its dependencies directly
                         if all(is_dependency_completed(dep) for dep in task.dependencies):
                            return task
        return None

    def add_epic(self, name: str, description: Optional[str] = None, dependencies: Optional[list[UUID]] = None) -> Optional[Epic]:
        """Adds a new epic to the plan."""
        if not self._agent_plan:
            return None
        epic = Epic(name=name, description=description, dependencies=dependencies or [])
        self._agent_plan.epics.append(epic)
        self.save_plan()
        return epic

    def add_task_to_epic(self, epic_id: UUID, name: str, description: Optional[str] = None, dependencies: Optional[list[UUID]] = None, effort_estimate: Optional[str] = None, priority: Optional[int] = None) -> Optional[Task]:
        """Adds a new task to a specific epic."""
        epic = self.get_item_by_id(epic_id)
        if isinstance(epic, Epic):
            task = Task(name=name, description=description, dependencies=dependencies or [], effort_estimate=effort_estimate, priority=priority)
            epic.tasks.append(task)
            self.save_plan()
            return task
        return None

    def add_subtask_to_task(self, task_id: UUID, name: str, description: Optional[str] = None, dependencies: Optional[list[UUID]] = None) -> Optional[Subtask]:
        """Adds a new subtask to a specific task."""
        task = self.get_item_by_id(task_id)
        if isinstance(task, Task):
            subtask = Subtask(name=name, description=description, dependencies=dependencies or [])
            task.subtasks.append(subtask)
            self.save_plan()
            return subtask
        return None
