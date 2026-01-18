"""
Integration of Collaborative Framework with Core Vibe

This module extends the core Vibe functionality to support
dual-model collaboration transparently.

Supports seamless integration via VIBE_LOCAL_MODEL environment variable:
- When VIBE_LOCAL_MODEL is set and Ollama is running, collaborative mode auto-enables
- Devstral-2 handles planning, architecture, and review
- The local model (e.g., Deepseek-Coder-v2) handles implementation, docs, and maintenance
"""

from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
import json
import traceback # Added import

from vibe.collaborative.collaborative_agent import CollaborativeAgent
from vibe.collaborative.collaborative_router import CollaborativeRouter
from vibe.collaborative.task_manager import TaskType, ModelRole
from vibe.collaborative.ollama_detector import (
    should_enable_collaborative_mode,
    check_ollama_availability,
    get_local_model_from_env,
    OllamaStatus,
)
from vibe.core.config import VibeConfig
from vibe.core.types import LLMMessage


class CollaborativeVibeIntegration:
    """
    Integrates collaborative framework with core Vibe functionality.

    This class provides methods to:
    - Detect when collaborative mode should be activated
    - Route prompts to the appropriate model
    - Manage collaborative sessions within Vibe
    - Automatically enable collaborative mode when VIBE_LOCAL_MODEL is set
    """

    def __init__(self, config: VibeConfig, auto_detect: bool = True):
        """
        Initialize collaborative integration.

        Args:
            config: The VibeConfig instance
            auto_detect: If True, automatically detect and enable collaborative mode
                        when VIBE_LOCAL_MODEL is set and Ollama is running
        """
        self.config = config
        self.collaborative_agent = None
        self.collaborative_router = None
        self.project_root = Path.cwd()
        self._collaborative_mode_enabled = False
        self._local_model_name: Optional[str] = None
        self._ollama_status: Optional[OllamaStatus] = None
        self._auto_enabled = False
        self._auto_enable_message: Optional[str] = None

        # Load collaborative settings from config
        self._load_collaborative_settings()

        # Auto-detect and enable collaborative mode if VIBE_LOCAL_MODEL is set
        if auto_detect:
            self._auto_detect_collaborative_mode()
    
    def _load_collaborative_settings(self):
        """Load collaborative settings from Vibe config."""
        # Check if collaborative mode is enabled in config
        collaborative_config = getattr(self.config, 'collaborative', None)
        if collaborative_config and getattr(collaborative_config, 'enabled', False):
            self._collaborative_mode_enabled = True
            
            # Initialize collaborative agent
            self._initialize_collaborative_agent()
    
    def _initialize_collaborative_agent(self):
        """Initialize the collaborative agent and router."""
        if self.collaborative_agent is None:
            self.collaborative_agent = CollaborativeAgent(self.project_root)
            
            # Configure models based on Vibe config
            self._configure_models_from_vibe_config()
            
        # Initialize collaborative router
        if self.collaborative_router is None:
            self.collaborative_router = CollaborativeRouter(self.project_root)
    
    def _configure_models_from_vibe_config(self):
        """Configure collaborative models based on Vibe settings."""
        if not self.collaborative_agent:
            return
            
        # Get model configurations from Vibe config
        collaborative_config = getattr(self.config, 'collaborative', None)
        if not collaborative_config:
            return
            
        # Configure planner model (Devstral-2)
        planner_config = getattr(collaborative_config, 'planner', None)
        if planner_config:
            self.collaborative_agent.configure_models(
                planner_endpoint=getattr(planner_config, 'endpoint', None),
                planner_model=getattr(planner_config, 'model', None)
            )
            
        # Configure implementer model (Deepseek-Coder-v2)
        implementer_config = getattr(collaborative_config, 'implementer', None)
        if implementer_config:
            self.collaborative_agent.configure_models(
                implementer_endpoint=getattr(implementer_config, 'endpoint', None),
                implementer_model=getattr(implementer_config, 'model', None)
            )

    def _auto_detect_collaborative_mode(self):
        """
        Auto-detect if collaborative mode should be enabled.

        Checks for VIBE_LOCAL_MODEL environment variable and Ollama availability.
        If both are present, automatically enables collaborative mode.
        """
        should_enable, message = should_enable_collaborative_mode()

        if should_enable:
            self._local_model_name = get_local_model_from_env()
            self._ollama_status = check_ollama_availability()
            self._auto_enabled = True
            self._auto_enable_message = message

            # Enable collaborative mode
            self.enable_collaborative_mode(True)

            # Refresh config from environment to ensure local model is used
            if self.collaborative_agent:
                self.collaborative_agent.model_coordinator.refresh_config_from_env()

    def get_auto_enable_status(self) -> Dict[str, Any]:
        """
        Get the auto-enable status information.

        Returns:
            Dictionary with auto-enable status details.
        """
        return {
            "auto_enabled": self._auto_enabled,
            "message": self._auto_enable_message,
            "local_model": self._local_model_name,
            "ollama_available": self._ollama_status.available if self._ollama_status else False,
            "ollama_error": self._ollama_status.error_message if self._ollama_status else None,
        }

    def get_planner_system_prompt_addition(self) -> str:
        """
        Get system prompt addition for Devstral (planner) to be aware of local models.

        This provides context to Devstral about the available specialized models
        for implementation tasks.
        """
        if not self._collaborative_mode_enabled:
            return ""

        from vibe.collaborative.ollama_detector import get_all_configured_models

        # Get configured models
        models = get_all_configured_models()
        model_info = []
        for role, model_name in models.items():
            if model_name:
                model_info.append(f"- **{role.value.upper()} model**: {model_name}")

        models_list = "\n".join(model_info) if model_info else f"- **Single model**: {self._local_model_name}"

        return f"""
## COLLABORATIVE VIBE FORK - IMPORTANT CONTEXT

You are running in a FORKED version of Mistral Vibe with collaborative multi-model support.
This is NOT the standard Vibe - it has been extended with a collaborative framework.

### How This Fork Works:

**Collaborative Mode is Active** - You are working with specialized local models via Ollama.

### Configured Models:
{models_list}

### CRITICAL: You MUST use the `delegate_to_local` tool for ALL implementation tasks

**IMPORTANT: This is NOT optional. The collaborative router will automatically detect
implementation tasks and route them appropriately. If you try to implement tasks
directly, the system will override your response and use the local models anyway.**

**When the user asks you to write code, create files, update documentation, review code, 
or any implementation task, you MUST:**
1. Use the `delegate_to_local` tool with the appropriate task_type
2. The specialized model will handle the implementation
3. You review the result and present it to the user

**Your Role (Devstral - Planner/Coordinator):**
- Plan the approach and break down tasks
- Use `delegate_to_local` tool to delegate to specialized models
- Review what the local models produce
- Coordinate between different models
- Answer questions about architecture and design

**Task Types and Model Routing:**
- `task_type: "code"` → CODE model - Writing or modifying any code
- `task_type: "refactor"` → CODE model - Code improvements and restructuring
- `task_type: "test"` → CODE model - Writing tests
- `task_type: "review"` → REVIEW model - Code review and quality analysis
- `task_type: "documentation"` → DOCS model - README, docstrings, comments
- `task_type: "gitignore"` → DOCS model - .gitignore updates
- `task_type: "cleanup"` → DOCS model - Project organization

**Automatic Routing and Safety Features:**

The collaborative router includes automatic features:
1. **OOM Error Handling**: If local models run out of memory, tasks automatically fall back to Devstral
2. **Multi-Instance Safety**: File-based locking prevents multiple Vibe instances from overwhelming the system
3. **Periodic Retry**: Failed tasks are automatically retried with exponential backoff
4. **Memory Pressure Detection**: System monitors for memory issues and adjusts routing accordingly

**Example workflows:**

User: "Create a function to validate emails"
You:
1. Plan: "I'll create an email validation function with regex"
2. Use delegate_to_local with task_type="code" and detailed instructions
3. Review the result from the CODE model
4. Present to user

User: "Review this authentication code for security issues"
You:
1. Use delegate_to_local with task_type="review" and the code to review
2. The REVIEW model analyzes for security, bugs, best practices
3. Present the review findings to user

**IMPORTANT SAFETY NOTES:**
- The system will automatically detect and handle OOM errors
- Multiple Vibe instances can run safely without overwhelming the system
- Tasks will be completed even if local models fail, by falling back to Devstral
- You should NEVER implement tasks directly - always use the delegate_to_local tool

REMEMBER: Do NOT write code directly. ALWAYS use the `delegate_to_local` tool for implementation tasks.
The collaborative router will enforce this automatically.
"""

    def is_collaborative_mode_enabled(self) -> bool:
        """Check if collaborative mode is enabled."""
        return self._collaborative_mode_enabled
    
    def enable_collaborative_mode(self, enable: bool = True):
        """Enable or disable collaborative mode."""
        self._collaborative_mode_enabled = enable
        if enable and self.collaborative_agent is None:
            self._initialize_collaborative_agent()
    
    def should_use_collaborative_routing(self, prompt: str) -> bool:
        """Determine if a prompt should use collaborative routing."""
        if not self.is_collaborative_mode_enabled():
            return False
            
        # Check for collaborative keywords or patterns
        collaborative_keywords = [
            'plan', 'architecture', 'design', 'strategy',
            'implement', 'code', 'write', 'create', 'build',
            'document', 'docs', 'documentation',
            'review', 'analyze', 'check', 'audit',
            'refactor', 'improve', 'optimize',
            'test', 'testing', 'unit test'
        ]
        
        prompt_lower = prompt.lower()
        return any(keyword in prompt_lower for keyword in collaborative_keywords)
    
    def route_prompt_collaboratively(self, prompt: str, messages: List[LLMMessage]) -> Dict[str, Any]:
        """Route a prompt through the collaborative framework with automatic routing and safety features."""
        if not self.collaborative_agent or not self.collaborative_router:
            return {"use_collaborative": False, "message": "Collaborative mode not initialized"}
            
        # Analyze the prompt to determine task type
        task_type, task_description = self._analyze_prompt_for_task(prompt, messages)
        
        if task_type is None:
            return {"use_collaborative": False, "message": "Prompt doesn't match collaborative patterns"}
            
        # Create a routing task with the collaborative router
        routing_task_id = self.collaborative_router.create_routing_task(
            prompt=prompt,
            task_type=task_type,
            priority=self._determine_priority_from_prompt(prompt)
        )
        
        # Route the task through the router (handles OOM, locking, retries automatically)
        routing_result = self.collaborative_router.route_task(routing_task_id)
        
        if routing_result['success']:
            # Also add to collaborative agent for tracking
            agent_task_id = self.collaborative_agent.add_custom_task(
                task_type=task_type,
                description=task_description,
                priority=self._determine_priority_from_prompt(prompt)
            )
            
            return {
                "use_collaborative": True,
                "task_id": agent_task_id,
                "routing_task_id": routing_task_id,
                "result": routing_result['result'],
                "model_used": routing_result['model_used'],
                "fallback_used": routing_result.get('fallback', False),
                "project_status": self.collaborative_agent.get_project_status()
            }
        else:
            # Handle routing failure (OOM, system busy, etc.)
            error = routing_result.get('error', 'Unknown routing error')
            oom_detected = routing_result.get('oom_detected', False)
            
            if oom_detected:
                # Fallback to Devstral automatically
                fallback_result = self._handle_oom_fallback(prompt, task_type, task_description)
                return fallback_result
            elif 'retry_after' in routing_result:
                # System busy, suggest retry
                return {
                    "use_collaborative": True,
                    "task_id": routing_task_id,
                    "status": "system_busy",
                    "message": f"System busy: {error}",
                    "retry_after": routing_result['retry_after']
                }
            else:
                return {
                    "use_collaborative": True,
                    "task_id": routing_task_id,
                    "status": "failed",
                    "message": f"Routing failed: {error}"
                }
    
    def _handle_oom_fallback(self, prompt: str, task_type: TaskType, task_description: str) -> Dict[str, Any]:
        """Handle OOM error by falling back to Devstral."""
        # Create a task that will be executed by Devstral
        agent_task_id = self.collaborative_agent.add_custom_task(
            task_type=task_type,
            description=f"[OOM FALLBACK] {task_description}",
            priority=1  # High priority for fallback tasks
        )
        
        # Execute the task immediately with Devstral
        result = self.collaborative_agent.execute_next_task()
        
        if result['status'] == 'completed':
            return {
                "use_collaborative": True,
                "task_id": agent_task_id,
                "result": result['result'],
                "model_used": "Devstral-2 (OOM Fallback)",
                "fallback_used": True,
                "oom_fallback": True,
                "project_status": result['project_status']
            }
        else:
            return {
                "use_collaborative": True,
                "task_id": agent_task_id,
                "status": "fallback_queued",
                "message": "OOM fallback task added to queue"
            }
    
    def check_routing_task_status(self, routing_task_id: str) -> Dict[str, Any]:
        """Check the status of a routing task."""
        if not self.collaborative_router:
            return {"error": "Collaborative router not initialized"}
        
        return self.collaborative_router.get_task_status(routing_task_id)
    
    def get_system_safety_status(self) -> Dict[str, Any]:
        """Get current system safety status including memory pressure and locks."""
        if not self.collaborative_router:
            return {"error": "Collaborative router not initialized"}
        
        return self.collaborative_router.get_system_status()
    
    def _analyze_prompt_for_task(self, prompt: str, messages: List[LLMMessage]) -> Tuple[Optional[TaskType], str]:
        """Analyze a prompt to determine the appropriate task type."""
        prompt_lower = prompt.lower()
        
        # Check for planning/architecture tasks (Devstral-2)
        if any(keyword in prompt_lower for keyword in ['plan', 'architecture', 'design', 'strategy', 'roadmap']):
            return TaskType.PLANNING, prompt
            
        if any(keyword in prompt_lower for keyword in ['review', 'analyze', 'check', 'audit', 'quality']):
            return TaskType.CODE_REVIEW, prompt
            
        # Check for implementation tasks (Deepseek-Coder-v2)
        if any(keyword in prompt_lower for keyword in ['implement', 'code', 'write', 'create', 'build', 'function', 'class', 'method']):
            return TaskType.CODE_IMPLEMENTATION, prompt
            
        if any(keyword in prompt_lower for keyword in ['document', 'docs', 'documentation', 'write docs', 'api docs']):
            return TaskType.DOCUMENTATION, prompt
            
        if any(keyword in prompt_lower for keyword in ['refactor', 'improve', 'optimize', 'clean up']):
            return TaskType.REFACTORING, prompt
            
        if any(keyword in prompt_lower for keyword in ['test', 'testing', 'write tests', 'unit tests']):
            return TaskType.TESTING, prompt
            
        return None, prompt
    
    def _determine_priority_from_prompt(self, prompt: str) -> int:
        """Determine task priority based on prompt urgency indicators."""
        prompt_lower = prompt.lower()
        
        # High priority indicators
        if any(indicator in prompt_lower for indicator in ['urgent', 'critical', 'important', 'priority', 'asap']):
            return 1  # Highest priority
            
        # Medium priority indicators
        if any(indicator in prompt_lower for indicator in ['soon', 'next', 'soon', 'required']):
            return 2
            
        # Default priority
        return 3
    
    def _get_model_for_task_type(self, task_type: TaskType) -> str:
        """Get the model name for a given task type."""
        if task_type in [TaskType.PLANNING, TaskType.ARCHITECTURE, TaskType.CODE_REVIEW]:
            return "Devstral-2 (Planner)"
        else:
            return "Deepseek-Coder-v2 (Implementer)"
    
    def get_collaborative_status(self) -> Dict[str, Any]:
        """Get the current status of collaborative work."""
        if not self.collaborative_agent:
            return {"enabled": False, "message": "Collaborative mode disabled"}
            
        return {
            "enabled": True,
            "status": self.collaborative_agent.get_project_status(),
            "collaboration_summary": self.collaborative_agent.get_collaboration_summary()
        }
    
    def get_collaborative_suggestions(self, current_context: str) -> List[Dict[str, Any]]:
        """Get suggestions for collaborative actions based on current context."""
        if not self.is_collaborative_mode_enabled():
            return []
            
        suggestions = []
        context_lower = current_context.lower()
        
        # Suggest planning if we're starting something new
        if any(indicator in context_lower for indicator in ['new project', 'start', 'begin', 'initiate']):
            suggestions.append({
                "type": "planning",
                "description": "Create a comprehensive development plan",
                "model": "Devstral-2",
                "command": "/collaborative plan " + current_context
            })
            
        # Suggest implementation if we have a plan
        if any(indicator in context_lower for indicator in ['plan ready', 'design complete', 'architecture done']):
            suggestions.append({
                "type": "implementation",
                "description": "Start implementing the planned features",
                "model": "Deepseek-Coder-v2",
                "command": "/collaborative implement"
            })
            
        # Suggest documentation if we have code
        if any(indicator in context_lower for indicator in ['code complete', 'implementation done', 'finished coding']):
            suggestions.append({
                "type": "documentation",
                "description": "Generate comprehensive documentation",
                "model": "Deepseek-Coder-v2",
                "command": "/collaborative document"
            })
            
        return suggestions
    
    def handle_collaborative_command(self, command: str, args: str) -> Dict[str, Any]:
        """Handle collaborative-specific commands."""
        if not self.collaborative_agent:
            return {"success": False, "message": "Collaborative mode not enabled"}
            
        command = command.lower()
        
        if command == "status":
            return {
                "success": True,
                "status": self.get_collaborative_status()
            }
            
        elif command == "enable":
            self.enable_collaborative_mode(True)
            return {
                "success": True,
                "message": "Collaborative mode enabled"
            }
            
        elif command == "disable":
            self.enable_collaborative_mode(False)
            return {
                "success": True,
                "message": "Collaborative mode disabled"
            }
            
        elif command == "plan":
            result = self.collaborative_agent.start_project("Current Project", args)
            return {
                "success": True,
                "plan": result
            }
            
        elif command == "implement":
            result = self.collaborative_agent.execute_next_task()
            return {
                "success": True,
                "implementation": result
            }
            
        elif command == "document":
            docs = self.collaborative_agent.generate_documentation(args)
            return {
                "success": True,
                "documentation": docs
            }
            
        elif command == "review":
            review = self.collaborative_agent.review_code(args)
            return {
                "success": True,
                "review": review
            }
        
        else:
            return {
                "success": False,
                "message": f"Unknown collaborative command: {command}"
            }
    
    def integrate_with_vibe_config(self, config: VibeConfig) -> VibeConfig:
        """Integrate collaborative settings into Vibe config."""
        # Add collaborative section if not present
        if not hasattr(config, 'collaborative'):
            config.collaborative = type('CollaborativeConfig', (), {
                'enabled': False,
                'planner': type('PlannerConfig', (), {
                    'model': 'devstral-2',
                    'endpoint': 'http://localhost:11434/api/generate'
                }),
                'implementer': type('ImplementerConfig', (), {
                    'model': 'deepseek-coder-v2',
                    'endpoint': 'http://localhost:11434/api/generate'
                })
            })
            
        return config

    def start_ralph_loop(self, plan: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Initiate a Ralph loop with a given plan."""
        if not self.collaborative_agent:
            return {"success": False, "message": "Collaborative mode not enabled"}
        return self.collaborative_agent.start_ralph_loop(plan)

    def get_ralph_loop_status(self) -> Dict[str, Any]:
        """Get the current status of the active Ralph loop."""
        if not self.collaborative_agent:
            return {"success": False, "message": "Collaborative mode not enabled"}
        return self.collaborative_agent.get_ralph_loop_status()
    
    def execute_next_ralph_task(self) -> Dict[str, Any]:
        """Execute the next task in the active Ralph loop."""
        if not self.collaborative_agent:
            return {"success": False, "message": "Collaborative mode not enabled"}
        return self.collaborative_agent.execute_next_task()
    
    def execute_all_ralph_tasks(self) -> Dict[str, Any]:
        """Execute all pending tasks in the active Ralph loop."""
        if not self.collaborative_agent:
            return {"success": False, "message": "Collaborative mode not enabled"}
        return self.collaborative_agent.execute_all_tasks()

    def cancel_ralph_loop(self) -> Dict[str, Any]:
        """Cancel the active Ralph loop by clearing all tasks."""
        if not self.collaborative_agent:
            return {"success": False, "message": "Collaborative mode not enabled"}
        # This will clear all pending and in-progress tasks
        self.collaborative_agent.task_manager.tasks.clear()
        self.collaborative_agent.task_manager.task_queue.clear()
        self.collaborative_agent.task_manager.completed_tasks.clear()
        self.collaborative_agent.task_manager._save_tasks()
        return {"success": True, "message": "Ralph loop cancelled."}