"""
Task Manager for Dual-Model Collaboration

Manages the distribution of tasks between Devstral-2 and Deepseek-Coder-v2
based on task type and model capabilities.
"""

from enum import Enum, auto
from dataclasses import dataclass, field
from pathlib import Path
import json
import uuid
from datetime import datetime
from logging import getLogger # Added import

logger = getLogger(__name__) # Initialized logger

class TaskType(Enum):
    """Types of tasks that can be assigned to models."""
    PLANNING = auto()
    ARCHITECTURE = auto()
    CODE_IMPLEMENTATION = auto()
    DOCUMENTATION = auto()
    CODE_REVIEW = auto()
    REFACTORING = auto()
    TESTING = auto()
    MAINTENANCE = auto()
    REPOSITORY_HYGIENE = auto()

class TaskStatus(Enum):
    """Possible statuses for a collaborative task."""
    PENDING = auto()
    ASSIGNED = auto()
    IN_PROGRESS = auto()
    DEBUGGING = auto()
    COMPLETED = auto()
    BLOCKED = auto()

class ModelRole(Enum):
    """Roles assigned to different models."""
    PLANNER = "devstral-2"
    IMPLEMENTER = "deepseek-coder-v2"


@dataclass
class CollaborativeTask:
    """Represents a task in the collaborative workflow."""
    task_id: str
    task_type: TaskType
    description: str
    priority: int = 3  # 1-5 scale, 1 being highest
    status: TaskStatus = TaskStatus.PENDING
    assigned_to: ModelRole | None = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    dependencies: list[str] = field(default_factory=list)  # IDs of dependent tasks


class TaskManager:
    """Manages the lifecycle of collaborative tasks."""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.tasks: dict[str, CollaborativeTask] = {}
        self.task_queue: list[str] = []
        self.completed_tasks: list[str] = []
        self.task_history_file = project_root / ".vibe" / "collaborative_tasks.json"
        
        # Ensure .vibe directory exists
        self.task_history_file.parent.mkdir(exist_ok=True)
        
        # Load existing tasks if any
        self._load_tasks()
    
    def _load_tasks(self):
        """Load tasks from persistent storage."""
        if self.task_history_file.exists():
            try:
                with open(self.task_history_file, 'r') as f:
                    task_data = json.load(f)
                    for task_id, task_info in task_data.items():
                        task = CollaborativeTask(
                            task_id=task_id,
                            task_type=TaskType[task_info['task_type']],
                            description=task_info['description'],
                            priority=task_info.get('priority', 3),
                            status=TaskStatus[task_info['status']],
                            assigned_to=ModelRole(task_info['assigned_to']) if task_info.get('assigned_to') else None,
                            created_at=datetime.fromisoformat(task_info['created_at']),
                            updated_at=datetime.fromisoformat(task_info['updated_at']),
                            dependencies=task_info.get('dependencies', [])
                        )
                        self.tasks[task_id] = task
                        if task.status == TaskStatus.PENDING:
                            self.task_queue.append(task_id)
                        elif task.status == 'completed':
                            self.completed_tasks.append(task_id)
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning("Could not load tasks: %s", e) # Changed print to logger.warning
    
    def _save_tasks(self):
        """Save tasks to persistent storage."""
        task_data = {}
        for task_id, task in self.tasks.items():
            task_data[task_id] = {
                'task_type': task.task_type.name,
                'description': task.description,
                'priority': task.priority,
                'status': task.status.name,
                'assigned_to': task.assigned_to.value if task.assigned_to else None,
                'created_at': task.created_at.isoformat(),
                'updated_at': task.updated_at.isoformat(),
                'dependencies': task.dependencies
            }
        
        try: # Added try-except block
            with open(self.task_history_file, 'w') as f:
                json.dump(task_data, f, indent=2)
        except OSError as e:
            logger.warning("Could not save tasks to %s: %s", self.task_history_file, e) # Log error
    
    def create_task(
        self,
        task_type: TaskType,
        description: str,
        priority: int = 3,
        dependencies: list[str] | None = None,
    ) -> str:
        """Create a new collaborative task."""
        task_id = str(uuid.uuid4())
        
        task = CollaborativeTask(
            task_id=task_id,
            task_type=task_type,
            description=description,
            priority=priority,
            dependencies=dependencies or []
        )
        
        self.tasks[task_id] = task
        self.task_queue.append(task_id)
        self._save_tasks()
        
        return task_id
    
    def assign_task(self, task_id: str, model_role: ModelRole):
        """Assign a task to a specific model."""
        if task_id not in self.tasks:
            raise ValueError(f"Task {task_id} not found")
        
        task = self.tasks[task_id]
        task.assigned_to = model_role
        task.status = TaskStatus.ASSIGNED
        task.updated_at = datetime.now()
        self._save_tasks()
    
    def complete_task(self, task_id: str):
        """Mark a task as completed."""
        if task_id not in self.tasks:
            raise ValueError(f"Task {task_id} not found")
        
        task = self.tasks[task_id]
        task.status = TaskStatus.COMPLETED
        task.updated_at = datetime.now()
        
        if task_id in self.task_queue:
            self.task_queue.remove(task_id)
        self.completed_tasks.append(task_id)
        self._save_tasks()
    
    def get_next_task(self) -> tuple[str, CollaborativeTask] | None:
        """Get the next available task from the queue whose dependencies are met."""
        if not self.task_queue:
            return None
        
        # Sort by priority (lower numbers = higher priority)
        self.task_queue.sort(key=lambda tid: self.tasks[tid].priority)
        
        for task_id in list(self.task_queue): # Iterate over a copy to allow modification
            if self._is_task_blocked(task_id):
                task = self.tasks[task_id]
                if task.status != TaskStatus.BLOCKED: # Only update if status changed
                    task.status = TaskStatus.BLOCKED
                    task.updated_at = datetime.now()
                    self._save_tasks()
                continue
            
            # If not blocked, this is the next available task
            return task_id, self.tasks[task_id]
        
        return None # No unblocked tasks found
    
    def _is_task_blocked(self, task_id: str) -> bool:
        """Check if a task is blocked by uncompleted dependencies."""
        task = self.tasks[task_id]
        for dep_id in task.dependencies:
            if dep_id not in self.tasks or self.tasks[dep_id].status != TaskStatus.COMPLETED:
                return True
        return False
    
    def get_task_status(self) -> dict[str, int]:
        """Get summary of task statuses."""
        status_counts = {status.name: 0 for status in TaskStatus}
        
        for task in self.tasks.values():
            status_counts[task.status.name] += 1
        
        return status_counts
    
    def get_tasks_by_model(self, model_role: ModelRole) -> list[tuple[str, CollaborativeTask]]:
        """Get all tasks assigned to a specific model."""
        return [(tid, task) for tid, task in self.tasks.items() 
                if task.assigned_to == model_role and task.status != TaskStatus.COMPLETED]

    def auto_assign_tasks(self):
        """Automatically assign tasks based on task type and model capabilities."""
        # Task type to model mapping
        task_assignment_rules = {
            TaskType.PLANNING: ModelRole.PLANNER,
            TaskType.ARCHITECTURE: ModelRole.PLANNER,
            TaskType.CODE_REVIEW: ModelRole.PLANNER,
            TaskType.CODE_IMPLEMENTATION: ModelRole.IMPLEMENTER,
            TaskType.DOCUMENTATION: ModelRole.IMPLEMENTER,
            TaskType.REFACTORING: ModelRole.IMPLEMENTER,
            TaskType.TESTING: ModelRole.IMPLEMENTER,
            TaskType.MAINTENANCE: ModelRole.IMPLEMENTER,
            TaskType.REPOSITORY_HYGIENE: ModelRole.IMPLEMENTER,
        }
        
        for task_id, task in self.tasks.items():
            if task.status == TaskStatus.PENDING and task_id in self.task_queue:
                assigned_role = task_assignment_rules.get(task.task_type)
                if assigned_role:
                    self.assign_task(task_id, assigned_role)

    def set_task_dependencies(self, task_id: str, dependencies: list[str]):
        """Set canonical dependencies for an existing task."""
        if task_id not in self.tasks:
            raise ValueError(f"Task {task_id} not found")

        task = self.tasks[task_id]
        task.dependencies = dependencies
        task.updated_at = datetime.now()
        self._save_tasks()
