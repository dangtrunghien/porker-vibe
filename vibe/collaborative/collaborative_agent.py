from pathlib import Path
from typing import Optional, Dict, Any
import json
from logging import getLogger # Added import

logger = getLogger(__name__) # Initialized logger

from .model_coordinator import ModelCoordinator
from .task_manager import TaskManager, TaskType, ModelRole, TaskStatus


class CollaborativeAgent:
    """
    Main collaborative agent that coordinates between Devstral-2 and Deepseek-Coder-v2.
    
    This agent implements the following workflow:
    1. Devstral-2 handles planning, architecture, and review
    2. Deepseek-Coder-v2 handles implementation, documentation, and maintenance
    3. Tasks are automatically distributed based on type
    4. Results are combined and reviewed iteratively
    """
    
    def __init__(self, project_root: Optional[Path] = None):
        """Initialize the collaborative agent."""
        self.project_root = project_root or Path.cwd()
        self.model_coordinator = ModelCoordinator(self.project_root)
        self.task_manager = self.model_coordinator.task_manager
        
        # Initialize project metadata
        self.project_metadata = self._load_project_metadata()
    
    def _load_project_metadata(self) -> Dict[str, Any]:
        """Load or initialize project metadata."""
        metadata_file = self.project_root / ".vibe" / "project_metadata.json"
        
        if metadata_file.exists():
            try:
                with open(metadata_file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e: # Added as e
                logger.warning("Could not load project metadata: %s", e) # Changed print to logger.warning
        
        # Return default metadata
        return {
            "project_name": self.project_root.name,
            "collaborative_mode": True,
            "models": {
                "planner": "devstral-2",
                "implementer": "deepseek-coder-v2"
            }
        }
    
    def _save_project_metadata(self):
        """Save project metadata."""
        metadata_file = self.project_root / ".vibe" / "project_metadata.json"
        metadata_file.parent.mkdir(exist_ok=True)
        
        with open(metadata_file, 'w') as f:
            json.dump(self.project_metadata, f, indent=2)
    
    def start_project(self, project_name: str, project_description: str) -> Dict[str, Any]:
        """Start a new collaborative development project."""
        self.project_metadata["project_name"] = project_name
        self.project_metadata["description"] = project_description
        self._save_project_metadata()
        
        # Start the collaborative session, which generates and parses the plan
        plan_data = self.model_coordinator.start_collaborative_session(project_description)
        
        return {
            "status": "Project planning complete",
            "project_name": project_name,
            "development_plan": plan_data, # This will now be the parsed plan
            "next_steps": "Review the plan and use start_ralph_loop() to begin implementation"
        }
    
    def execute_next_task(self) -> Dict[str, Any]:
        """Execute the next task in the collaborative workflow."""
        task_id, result = self.model_coordinator.execute_next_task()
        
        if task_id is None:
            return {
                "status": "no_tasks",
                "message": result or "No tasks available"
            }
        
        return {
            "status": "completed",
            "task_id": task_id,
            "result": result,
            "project_status": self.get_project_status()
        }
    
    def execute_all_tasks(self) -> Dict[str, Any]:
        """Execute all pending tasks in the workflow."""
        results = []
        
        while True:
            task_result = self.execute_next_task()
            
            if task_result["status"] == "no_tasks":
                break
            
            results.append({
                "task_id": task_result["task_id"],
                "result": task_result["result"]
            })
        
        return {
            "status": "all_tasks_completed",
            "completed_tasks": len(results),
            "results": results,
            "final_status": self.get_project_status()
        }
    
    def add_custom_task(self, task_type: TaskType, description: str, 
                       priority: int = 3, dependencies: Optional[list] = None) -> str:
        """Add a custom task to the workflow."""
        task_id = self.task_manager.create_task(
            task_type=task_type,
            description=description,
            priority=priority,
            dependencies=dependencies
        )
        
        # Auto-assign the task
        self.task_manager.auto_assign_tasks()
        
        return task_id

    def start_ralph_loop(self, plan: list[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Initializes and starts a Ralph Wiggum-like iterative loop based on a given plan.
        The plan is a list of tasks with types, descriptions, names, and optional dependencies (referenced by name).
        """
        task_name_to_id = {}
        tasks_with_raw_dependencies = []

        # First pass: Create all tasks and map their names to IDs
        for task_spec in plan:
            task_type = TaskType[task_spec["task_type"]]
            description = task_spec["description"]
            task_name = task_spec.get("name") # Expecting a unique name for each task

            if not task_name:
                logger.warning("Task spec is missing a 'name' field. Skipping task: %s", description)
                continue

            task_id = self.task_manager.create_task(
                task_type=task_type,
                description=description,
                priority=task_spec.get("priority", 3),
                dependencies=[] # Initialize with empty dependencies
            )
            task_name_to_id[task_name] = task_id
            tasks_with_raw_dependencies.append((task_id, task_spec.get("dependencies", [])))

        # Second pass: Resolve dependencies using the created task_ids
        for task_id, raw_dependencies in tasks_with_raw_dependencies:
            resolved_dependencies = []
            for dep_name in raw_dependencies:
                if dep_name in task_name_to_id:
                    resolved_dependencies.append(task_name_to_id[dep_name])
                else:
                    logger.warning(f"Dependency '{dep_name}' for task '{self.task_manager.tasks[task_id].description}' not found in the plan. Skipping this dependency.")
            
            if resolved_dependencies:
                self.task_manager.set_task_dependencies(task_id, resolved_dependencies)
        
        self.task_manager.auto_assign_tasks() # Auto-assign tasks after dependencies are set

        return {
            "status": "Ralph loop initiated",
            "total_tasks": len(task_name_to_id),
            "task_ids": list(task_name_to_id.values()),
            "next_steps": "Use execute_next_task() to begin iterating through the plan."
        }
    
    def get_project_status(self) -> Dict[str, Any]:
        """Get the current status of the collaborative project."""
        status = self.model_coordinator.get_project_status()
        
        return {
            "project_name": self.project_metadata.get("project_name", "Unnamed Project"),
            "description": self.project_metadata.get("description", ""),
            "task_status": status["task_status"],
            "models": status["models_configured"],
            "pending_tasks": status["pending_tasks"],
            "completed_tasks": status["completed_tasks"],
            "total_tasks": len(self.task_manager.tasks)
        }
    
    def get_tasks_for_model(self, model_role: ModelRole) -> Dict[str, Any]:
        """Get all tasks assigned to a specific model."""
        tasks = self.task_manager.get_tasks_by_model(model_role)
        
        return {
            "model": model_role.value,
            "task_count": len(tasks),
            "tasks": [
                {
                    "task_id": task_id,
                    "type": task.task_type.name,
                    "description": task.description,
                    "priority": task.priority,
                    "status": task.status
                }
                for task_id, task in tasks
            ]
        }
    
    def review_code(self, code_content: str, file_path: Optional[str] = None) -> str:
        """Request a code review from the planner model (Devstral-2)."""
        context = f"File: {file_path}\n\n" if file_path else ""
        
        prompt = f"""{context}Please perform a comprehensive code review of the following code:

```
{code_content}
```

Your review should include:
1. Code quality assessment
2. Potential bugs or issues
3. Security concerns
4. Performance considerations
5. Adherence to best practices
6. Suggestions for improvement

Please provide your review in a structured format."""
        
        return self.model_coordinator.query_model(ModelRole.PLANNER, prompt)
    
    def generate_documentation(self, subject: str, context: Optional[str] = None) -> str:
        """Generate documentation using the implementer model (Deepseek-Coder-v2)."""
        context_text = f"\n\nContext: {context}" if context else ""
        
        prompt = f"""Please generate comprehensive documentation for the following subject:

{subject}

{context_text}

The documentation should include:
1. Overview and purpose
2. Technical details and specifications
3. Usage examples
4. API reference (if applicable)
5. Best practices
6. Troubleshooting information

Please provide the documentation in Markdown format."""
        
        return self.model_coordinator.query_model(ModelRole.IMPLEMENTER, prompt)
    
    def refactor_code(self, code_content: str, requirements: str) -> str:
        """Request code refactoring from the implementer model."""
        prompt = f"""Please refactor the following code according to these requirements:

Requirements:
{requirements}

Original Code:
```
{code_content}
```

Please provide:
1. The refactored code
2. Explanation of changes made
3. Benefits of the refactoring
4. Any breaking changes or considerations

Refactored Code:"""
        
        return self.model_coordinator.query_model(ModelRole.IMPLEMENTER, prompt)
    
    def configure_models(self, planner_endpoint: Optional[str] = None,
                        implementer_endpoint: Optional[str] = None,
                        planner_model: Optional[str] = None,
                        implementer_model: Optional[str] = None):
        """Configure the model endpoints and names."""
        if planner_endpoint or planner_model:
            current_config = self.model_coordinator.models[ModelRole.PLANNER]
            self.model_coordinator.update_model_config(
                ModelRole.PLANNER,
                planner_model or current_config.model_name,
                planner_endpoint or current_config.endpoint
            )
        
        if implementer_endpoint or implementer_model:
            current_config = self.model_coordinator.models[ModelRole.IMPLEMENTER]
            self.model_coordinator.update_model_config(
                ModelRole.IMPLEMENTER,
                implementer_model or current_config.model_name,
                implementer_endpoint or current_config.endpoint
            )
        
        # Update metadata
        if planner_model:
            self.project_metadata["models"]["planner"] = planner_model
        if implementer_model:
            self.project_metadata["models"]["implementer"] = implementer_model
        
        self._save_project_metadata()
        
        return self.get_project_status()
    
    def get_collaboration_summary(self) -> Dict[str, Any]:
        """Get a summary of the collaborative work done so far."""
        return {
            "project": self.project_metadata,
            "collaboration_stats": {
                "total_tasks": len(self.task_manager.tasks),
                "completed_tasks": len(self.task_manager.completed_tasks),
                "pending_tasks": len(self.task_manager.task_queue),
                "planner_tasks": len(self.task_manager.get_tasks_by_model(ModelRole.PLANNER)),
                "implementer_tasks": len(self.task_manager.get_tasks_by_model(ModelRole.IMPLEMENTER))
            },
            "models_used": {
                "planner": self.project_metadata["models"]["planner"],
                "implementer": self.project_metadata["models"]["implementer"]
            }
        }
    
    def get_ralph_loop_status(self) -> Dict[str, Any]:
        """
        Get the current status of the ongoing Ralph Wiggum-like iterative loop.
        Provides an overview of tasks, their statuses, and overall progress.
        """
        task_status_counts = self.task_manager.get_task_status()
        total_tasks = len(self.task_manager.tasks)
        completed_tasks = task_status_counts.get(TaskStatus.COMPLETED.name, 0)
        
        return {
            "loop_active": total_tasks > 0 and completed_tasks < total_tasks,
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "pending_tasks": task_status_counts.get(TaskStatus.PENDING.name, 0),
            "assigned_tasks": task_status_counts.get(TaskStatus.ASSIGNED.name, 0),
            "in_progress_tasks": task_status_counts.get(TaskStatus.IN_PROGRESS.name, 0),
            "debugging_tasks": task_status_counts.get(TaskStatus.DEBUGGING.name, 0),
            "blocked_tasks": task_status_counts.get(TaskStatus.BLOCKED.name, 0),
            "task_breakdown": task_status_counts,
            "next_steps": "Continue executing tasks using execute_next_task() or execute_all_tasks()."
                           if total_tasks > 0 and completed_tasks < total_tasks else "Loop is completed or not started."
        }