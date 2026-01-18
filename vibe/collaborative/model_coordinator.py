"""
Model Coordinator for Dual-Model Collaboration

Handles communication and coordination between Devstral-2 and a local model via Ollama.
Supports VIBE_LOCAL_MODEL environment variable for seamless configuration.
"""

from pathlib import Path
import json
import requests
from datetime import datetime

from .task_manager import TaskManager, TaskType, ModelRole, CollaborativeTask
from .ollama_detector import (
    get_local_model_from_env,
    get_ollama_generate_endpoint,
    check_ollama_availability,
    OllamaStatus,
)


class ModelConfig:
    """Configuration for a model endpoint."""
    
    def __init__(self, model_name: str, endpoint: str, api_key: str | None = None):
        self.model_name = model_name
        self.endpoint = endpoint
        self.api_key = api_key
        self.headers = {"Content-Type": "application/json"}
        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"


class ModelCoordinator:
    """Coordinates communication between multiple models."""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.task_manager = TaskManager(project_root)
        self.models: dict[ModelRole, ModelConfig] = {}
        self.config_file = project_root / ".vibe" / "model_config.json"
        
        # Load or create default configuration
        self._load_or_create_config()
    
    def _load_or_create_config(self):
        """Load existing config or create default configuration."""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    config_data = json.load(f)
                    for role_name, model_config in config_data.items():
                        role = ModelRole(role_name)
                        self.models[role] = ModelConfig(
                            model_name=model_config['model_name'],
                            endpoint=model_config['endpoint'],
                            api_key=model_config.get('api_key')
                        )
            except (json.JSONDecodeError, KeyError) as e:
                print(f"Warning: Could not load model config: {e}")
                self._create_default_config()
        else:
            self._create_default_config()
    
    def _create_default_config(self):
        """Create default model configuration.

        Uses VIBE_LOCAL_MODEL environment variable if set for the implementer model.
        """
        # Check for local model from environment variable
        local_model = get_local_model_from_env()
        ollama_endpoint = get_ollama_generate_endpoint()

        # Use environment variable model if set, otherwise use default
        implementer_model = local_model if local_model else "deepseek-coder-v2"

        # Default configuration for local Ollama setup
        default_config = {
            ModelRole.PLANNER.value: {
                "model_name": "devstral-2",
                "endpoint": "http://localhost:11434/api/generate",
                "api_key": None
            },
            ModelRole.IMPLEMENTER.value: {
                "model_name": implementer_model,
                "endpoint": ollama_endpoint,
                "api_key": None
            }
        }
        
        # Save the configuration
        with open(self.config_file, 'w') as f:
            json.dump(default_config, f, indent=2)
        
        # Load the configuration into memory
        for role_name, model_config in default_config.items():
            role = ModelRole(role_name)
            self.models[role] = ModelConfig(
                model_name=model_config['model_name'],
                endpoint=model_config['endpoint'],
                api_key=model_config.get('api_key')
            )
    
    def update_model_config(
        self,
        role: ModelRole,
        model_name: str,
        endpoint: str,
        api_key: str | None = None,
    ):
        """Update configuration for a specific model role."""
        self.models[role] = ModelConfig(model_name, endpoint, api_key)
        
        # Save the updated configuration
        config_data: dict[str, dict[str, str | None]] = {}
        for model_role, model_config in self.models.items():
            config_data[model_role.value] = {
                "model_name": model_config.model_name,
                "endpoint": model_config.endpoint,
                "api_key": model_config.api_key
            }
        
        with open(self.config_file, 'w') as f:
            json.dump(config_data, f, indent=2)
    
    def query_model(self, role: ModelRole, prompt: str, context: dict | None = None) -> str:
        """Query a specific model with a prompt."""
        if role not in self.models:
            raise ValueError(f"No model configured for role: {role}")
        
        model_config = self.models[role]
        
        # Prepare the payload based on the endpoint type
        if "ollama" in model_config.endpoint:
            # Ollama API format
            payload = {
                "model": model_config.model_name,
                "prompt": prompt,
                "stream": False
            }
            if context:
                payload["context"] = context
        else:
            # Generic LLM API format
            payload = {
                "model": model_config.model_name,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7
            }
        
        try:
            response = requests.post(
                model_config.endpoint,
                headers=model_config.headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            
            if "ollama" in model_config.endpoint:
                return response.json()["response"]
            else:
                return response.json()["choices"][0]["message"]["content"]
                
        except requests.RequestException as e:
            print(f"Error querying {role.value} model: {e}")
            return f"Error: Could not query {role.value} model - {str(e)}"
    
    def start_collaborative_session(self, project_description: str):
        """Start a new collaborative development session."""
        # Step 1: Create planning task for Devstral-2
        self.task_manager.create_task(
            task_type=TaskType.PLANNING,
            description=f"Create development plan for: {project_description}",
            priority=1
        )
        
        # Step 2: Auto-assign tasks
        self.task_manager.auto_assign_tasks()
        
        # Step 3: Get the planning task
        next_task = self.task_manager.get_next_task()
        if not next_task:
            return "No tasks available for execution."

        task_id, planning_task = next_task
        
        # Step 4: Execute the planning task
        if planning_task.assigned_to == ModelRole.PLANNER:
            plan = self._execute_planning_task(planning_task.description)
            self.task_manager.complete_task(task_id)
            
            # Step 5: Create implementation tasks based on the plan
            self._create_implementation_tasks_from_plan(plan)
            
            return plan
        
        return "No tasks available for execution."
    
    def _execute_planning_task(self, task_description: str) -> str:
        """Execute a planning task using the planner model."""
        prompt = f"""You are an expert software architect. Please create a comprehensive development plan for the following project:

{task_description}

Your plan should include:
1. Overall architecture and components
2. Detailed task breakdown
3. Dependencies between tasks
4. Estimated priorities
5. Any technical considerations or challenges

Please provide the plan in JSON format with the following structure:
{{
  "project_name": "string",
  "architecture": "string",
  "tasks": [
    {{
      "name": "string",
      "type": "PLANNING|ARCHITECTURE|CODE_IMPLEMENTATION|DOCUMENTATION|CODE_REVIEW|REFACTORING|TESTING|MAINTENANCE|REPOSITORY_HYGIENE",
      "description": "string",
      "priority": 1-5,
      "dependencies": ["task_names"]
    }}
  ],
  "technical_considerations": "string"
}}"""
        
        plan_json = self.query_model(ModelRole.PLANNER, prompt)
        
        return plan_json
    
    def _create_implementation_tasks_from_plan(self, plan_json: str):
        """Create implementation tasks based on a development plan."""
        try:
            plan = json.loads(plan_json)
            
            task_name_to_id: dict[str, str] = {}
            dependency_names_by_task: dict[str, list[str]] = {}

            # Create a task for each item in the plan
            for task_info in plan.get("tasks", []):
                task_type = TaskType[task_info["type"]]
                task_description = task_info["description"]
                priority = task_info.get("priority", 3)

                task_id = self.task_manager.create_task(
                    task_type=task_type,
                    description=task_description,
                    priority=priority,
                    dependencies=[]
                )

                task_name = task_info.get("name")
                if task_name:
                    task_name_to_id[task_name] = task_id

                raw_dependencies = task_info.get("dependencies") or []
                dependency_names_by_task[task_id] = [
                    dep for dep in raw_dependencies if isinstance(dep, str)
                ]

            for task_id, dependency_names in dependency_names_by_task.items():
                resolved_dependencies = [
                    task_name_to_id[name]
                    for name in dependency_names
                    if name in task_name_to_id
                ]
                if resolved_dependencies:
                    self.task_manager.set_task_dependencies(task_id, resolved_dependencies)

            # Auto-assign the new tasks after dependencies are wired up
            self.task_manager.auto_assign_tasks()
            
        except json.JSONDecodeError as e:
            print(f"Error parsing plan JSON: {e}")
    
    def execute_next_task(self) -> tuple[str | None, str | None]:
        """Execute the next available task in the queue."""
        task_result = self.task_manager.get_next_task()
        
        if not task_result:
            return None, "No tasks available"
        
        task_id, task = task_result
        
        if task.assigned_to == ModelRole.PLANNER:
            # Planning/architecture/review task
            result = self._execute_planner_task(task)
        elif task.assigned_to == ModelRole.IMPLEMENTER:
            # Implementation task
            result = self._execute_implementer_task(task)
        else:
            return task_id, "Task not assigned to any model"
        
        # Mark task as completed
        self.task_manager.complete_task(task_id)
        
        return task_id, result
    
    def _execute_planner_task(self, task: CollaborativeTask) -> str:
        """Execute a task assigned to the planner model."""
        prompt = self._create_task_prompt(task)
        return self.query_model(ModelRole.PLANNER, prompt)
    
    def _execute_implementer_task(self, task: CollaborativeTask) -> str:
        """Execute a task assigned to the implementer model."""
        prompt = self._create_task_prompt(task)
        return self.query_model(ModelRole.IMPLEMENTER, prompt)
    
    def _create_task_prompt(self, task: CollaborativeTask) -> str:
        """Create a prompt for executing a specific task."""
        base_prompt = f"""Task: {task.description}

Task Type: {task.task_type.name}
Priority: {task.priority}
"""
        
        if task.dependencies:
            base_prompt += f"\nDependencies: {', '.join(task.dependencies)}"
        
        base_prompt += "\n\nPlease complete this task:"
        
        # Add task-specific instructions
        if task.task_type == TaskType.CODE_IMPLEMENTATION:
            base_prompt += "\n\nWrite clean, well-documented code. Follow best practices and include appropriate tests."
        elif task.task_type == TaskType.DOCUMENTATION:
            base_prompt += "\n\nWrite comprehensive documentation. Include examples, usage instructions, and technical details."
        elif task.task_type == TaskType.CODE_REVIEW:
            base_prompt += "\n\nPerform a thorough code review. Check for bugs, security issues, performance problems, and adherence to best practices."
        
        return base_prompt
    
    def get_project_status(self) -> dict:
        """Get the current status of the collaborative project."""
        return {
            "task_status": self.task_manager.get_task_status(),
            "models_configured": {role.value: config.model_name for role, config in self.models.items()},
            "pending_tasks": len(self.task_manager.task_queue),
            "completed_tasks": len(self.task_manager.completed_tasks)
        }

    def check_ollama_status(self) -> OllamaStatus:
        """Check if Ollama is available and return status."""
        return check_ollama_availability()

    def get_local_model_name(self) -> str | None:
        """Get the configured local model name from VIBE_LOCAL_MODEL."""
        return get_local_model_from_env()

    def refresh_config_from_env(self):
        """
        Refresh model configuration from environment variables.

        This allows dynamic reconfiguration when VIBE_LOCAL_MODEL changes.
        """
        local_model = get_local_model_from_env()
        if local_model:
            ollama_endpoint = get_ollama_generate_endpoint()
            self.update_model_config(
                ModelRole.IMPLEMENTER,
                local_model,
                ollama_endpoint
            )

    def get_implementer_model_info(self) -> dict[str, object]:
        """Get information about the implementer model configuration."""
        implementer = self.models.get(ModelRole.IMPLEMENTER)
        if not implementer:
            return {"configured": False}

        return {
            "configured": True,
            "model_name": implementer.model_name,
            "endpoint": implementer.endpoint,
            "from_env": get_local_model_from_env() is not None
        }
