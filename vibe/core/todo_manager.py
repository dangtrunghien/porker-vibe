"""
Todo Manager for Vibe CLI

Manages agent todos during conversation - persistent per-project.
Similar to Claude Code's TodoWrite functionality.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional
from uuid import UUID, uuid4


class TodoStatus(str, Enum):
    """Status of a todo item."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


@dataclass
class TodoItem:
    """A single todo item."""
    id: UUID = field(default_factory=uuid4)
    content: str = ""
    active_form: str = ""  # Present continuous form (e.g., "Running tests")
    status: TodoStatus = TodoStatus.PENDING
    parent_id: Optional[UUID] = None  # For hierarchical organization
    order: int = 0  # Display order within parent
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": str(self.id),
            "content": self.content,
            "active_form": self.active_form,
            "status": self.status.value,
            "parent_id": str(self.parent_id) if self.parent_id else None,
            "order": self.order,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> TodoItem:
        """Create from dictionary."""
        parent_id_str = data.get("parent_id")
        return cls(
            id=UUID(data["id"]),
            content=data["content"],
            active_form=data["active_form"],
            status=TodoStatus(data["status"]),
            parent_id=UUID(parent_id_str) if parent_id_str else None,
            order=data.get("order", 0),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
        )


class TodoManager:
    """
    Manages todos for the current agent session.
    Todos are persistent per-project and stored in .vibe/todos.json
    """

    def __init__(self, project_path: Path):
        self.project_path = project_path
        self._todos_file_path = self._get_todos_file_path()
        self._todos: list[TodoItem] = []
        self.load_todos()

    def _get_todos_file_path(self) -> Path:
        """Get the path where todos JSON will be stored."""
        vibe_path = self.project_path / ".vibe"
        vibe_path.mkdir(parents=True, exist_ok=True)
        return vibe_path / "todos.json"

    def load_todos(self) -> None:
        """Load todos from file."""
        if not self._todos_file_path.exists():
            self._todos = []
            return

        try:
            with self._todos_file_path.open("r", encoding="utf-8") as f:
                todos_data = json.load(f)
            self._todos = [TodoItem.from_dict(item) for item in todos_data]
        except (json.JSONDecodeError, FileNotFoundError, IOError):
            self._todos = []

    def save_todos(self) -> None:
        """Save todos to file."""
        with self._todos_file_path.open("w", encoding="utf-8") as f:
            json.dump([todo.to_dict() for todo in self._todos], f, indent=2)

    def set_todos(self, todos: list[dict]) -> None:
        """
        Set todos from a list of dictionaries.
        Expected format: [{"content": "...", "status": "pending|in_progress|completed", "activeForm": "..."}]
        """
        new_todos = []
        for todo_data in todos:
            # Try to find existing todo by content to preserve ID
            existing_todo = None
            for existing in self._todos:
                if existing.content == todo_data.get("content", ""):
                    existing_todo = existing
                    break

            if existing_todo:
                # Update existing todo
                existing_todo.status = TodoStatus(todo_data.get("status", "pending"))
                existing_todo.active_form = todo_data.get("activeForm", "")
                existing_todo.order = len(new_todos)
                existing_todo.updated_at = time.time()
                new_todos.append(existing_todo)
            else:
                # Create new todo
                new_todos.append(TodoItem(
                    content=todo_data.get("content", ""),
                    active_form=todo_data.get("activeForm", ""),
                    status=TodoStatus(todo_data.get("status", "pending")),
                    order=len(new_todos),
                ))

        self._todos = new_todos
        self.save_todos()

    def get_todos(self) -> list[TodoItem]:
        """Get all todos."""
        return self._todos.copy()

    def get_todos_in_order(self) -> list[TodoItem]:
        """Get todos sorted by order field."""
        return sorted(self._todos, key=lambda t: t.order)

    def clear_todos(self) -> None:
        """Clear all todos."""
        self._todos = []
        self.save_todos()

    def get_active_todo(self) -> Optional[TodoItem]:
        """Get the currently in-progress todo."""
        for todo in self._todos:
            if todo.status == TodoStatus.IN_PROGRESS:
                return todo
        return None

    def get_stats(self) -> dict:
        """Get todo statistics."""
        total = len(self._todos)
        completed = sum(1 for todo in self._todos if todo.status == TodoStatus.COMPLETED)
        in_progress = sum(1 for todo in self._todos if todo.status == TodoStatus.IN_PROGRESS)
        pending = sum(1 for todo in self._todos if todo.status == TodoStatus.PENDING)

        return {
            "total": total,
            "completed": completed,
            "in_progress": in_progress,
            "pending": pending,
        }

    def are_all_complete(self) -> bool:
        """Check if all todos are completed."""
        if not self._todos:
            return False
        return all(todo.status == TodoStatus.COMPLETED for todo in self._todos)

    def has_active_work(self) -> bool:
        """Check if there are any pending or in-progress todos."""
        return any(
            todo.status in {TodoStatus.PENDING, TodoStatus.IN_PROGRESS}
            for todo in self._todos
        )
