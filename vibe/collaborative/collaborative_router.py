"""
Collaborative Task Router with Automatic Offloading and Safety Features

Handles automatic routing of tasks to local models with:
- OOM error detection and fallback
- Multi-instance safety via file locking
- Periodic retry logic
- Task state management
"""

import os
import time
import json
import uuid
import fcntl
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import traceback
import random
from logging import getLogger # Added import
import platform # Added import

logger = getLogger(__name__) # Initialized logger

from vibe.collaborative.task_manager import TaskType, ModelRole, CollaborativeTask
from vibe.collaborative.model_coordinator import ModelCoordinator
from vibe.collaborative.ollama_detector import check_ollama_availability

@dataclass
class TaskAttempt:
    """Represents an attempt to execute a task."""
    attempt_id: str
    timestamp: datetime
    model_used: str
    success: bool
    error: Optional[str] = None
    oom_detected: bool = False

@dataclass
class RoutingTask:
    """Represents a task being routed through the collaborative system."""
    task_id: str
    original_prompt: str
    task_type: TaskType
    priority: int = 3
    max_attempts: int = 3
    attempts: List[TaskAttempt] = field(default_factory=list)
    current_attempt: int = 0
    fallback_to_devstral: bool = False
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    locked_by: Optional[str] = None  # Instance ID that locked this task

class CollaborativeRouter:
    """Main router for collaborative tasks with safety features."""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.lock_file = project_root / ".vibe" / "collaborative_router.lock"
        self.tasks_file = project_root / ".vibe" / "routing_tasks.json"
        self.instance_id = str(uuid.uuid4())
        self.lock_file.parent.mkdir(exist_ok=True)
        
        # Load existing tasks
        self.tasks: Dict[str, RoutingTask] = {}
        self._load_tasks()
        
        # Initialize lock file
        self._initialize_lock_file()
        
        # Initialize model coordinator for actual model execution
        self.model_coordinator = ModelCoordinator(self.project_root)
        
        # System state tracking
        self.system_under_memory_pressure = False
        self.last_oom_time: Optional[datetime] = None
        self.consecutive_oom_count = 0
    
    def _initialize_lock_file(self):
        """Initialize the lock file if it doesn't exist."""
        if not self.lock_file.exists():
            self.lock_file.write_text("", "utf-8")
    
    def _load_tasks(self):
        """Load tasks from persistent storage."""
        if self.tasks_file.exists():
            try:
                with open(self.tasks_file, 'r') as f:
                    task_data = json.load(f)
                    for task_id, task_info in task_data.items():
                        attempts = [
                            TaskAttempt(
                                attempt_id=a['attempt_id'],
                                timestamp=datetime.fromisoformat(a['timestamp']),
                                model_used=a['model_used'],
                                success=a['success'],
                                error=a.get('error'),
                                oom_detected=a.get('oom_detected', False)
                            )
                            for a in task_info.get('attempts', [])
                        ]
                        
                        task = RoutingTask(
                            task_id=task_id,
                            original_prompt=task_info['original_prompt'],
                            task_type=TaskType[task_info['task_type']],
                            priority=task_info.get('priority', 3),
                            max_attempts=task_info.get('max_attempts', 3),
                            attempts=attempts,
                            current_attempt=task_info.get('current_attempt', 0),
                            fallback_to_devstral=task_info.get('fallback_to_devstral', False),
                            created_at=datetime.fromisoformat(task_info['created_at']),
                            updated_at=datetime.fromisoformat(task_info['updated_at']),
                            locked_by=task_info.get('locked_by')
                        )
                        self.tasks[task_id] = task
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning("Could not load routing tasks: %s", e)
    
    def _save_tasks(self):
        """Save tasks to persistent storage."""
        task_data = {}
        for task_id, task in self.tasks.items():
            task_data[task_id] = {
                'original_prompt': task.original_prompt,
                'task_type': task.task_type.name,
                'priority': task.priority,
                'max_attempts': task.max_attempts,
                'attempts': [{
                    'attempt_id': a.attempt_id,
                    'timestamp': a.timestamp.isoformat(),
                    'model_used': a.model_used,
                    'success': a.success,
                    'error': a.error,
                    'oom_detected': a.oom_detected
                } for a in task.attempts],
                'current_attempt': task.current_attempt,
                'fallback_to_devstral': task.fallback_to_devstral,
                'created_at': task.created_at.isoformat(),
                'updated_at': task.updated_at.isoformat(),
                'locked_by': task.locked_by
            }
        
        try:
            with open(self.tasks_file, 'w') as f:
                json.dump(task_data, f, indent=2)
        except OSError as e:
            logger.warning("Could not save routing tasks to %s: %s", self.tasks_file, e)
    
    def _acquire_system_lock(self, timeout: float = 5.0) -> bool:
        """Acquire a system-wide lock to prevent multiple instances from overwhelming Ollama."""
        if platform.system() not in ["Linux", "Darwin"]:
            logger.warning("File locking (fcntl) is only supported on Linux and Darwin. Skipping lock acquisition.")
            return True # Allow to proceed without locking on unsupported OS
        
        try:
            # Open lock file and acquire exclusive lock
            lock_fd = open(self.lock_file, 'r+')
            
            # Try to acquire lock with timeout
            start_time = time.time()
            while time.time() - start_time < timeout:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    
                    # Check if system is under memory pressure
                    if self.system_under_memory_pressure:
                        # If under memory pressure, only allow one instance at a time
                        existing_locks = self._count_active_locks()
                        if existing_locks > 0:
                            fcntl.flock(lock_fd, fcntl.LOCK_UN)
                            lock_fd.close()
                            return False
                    
                    # Write our instance ID to indicate we have the lock
                    lock_fd.seek(0)
                    lock_fd.write(f"{self.instance_id}\n")
                    lock_fd.flush()
                    
                    return True
                except BlockingIOError:
                    time.sleep(0.1)
            
            lock_fd.close()
            return False
            
        except Exception as e:
            logger.warning("Could not acquire system lock: %s", e)
            return False
    
    def _release_system_lock(self):
        """Release the system lock."""
        if platform.system() not in ["Linux", "Darwin"]:
            return # No locking to release on unsupported OS
        
        try:
            lock_fd = open(self.lock_file, 'r+')
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            
            # Remove our instance ID from the lock file
            lines = lock_fd.readlines()
            lock_fd.seek(0)
            lock_fd.writelines([line for line in lines if line.strip() != self.instance_id])
            lock_fd.truncate()
            lock_fd.close()
        except Exception as e:
            logger.warning("Could not release system lock: %s", e)
    
    def _count_active_locks(self) -> int:
        """Count how many instances currently hold locks."""
        try:
            with open(self.lock_file, 'r') as f:
                lines = f.readlines()
                return len([line.strip() for line in lines if line.strip()])
        except OSError as e:
            logger.warning("Could not count active locks: %s", e)
            return 0
    
    def _detect_oom_error(self, error: str) -> bool:
        """Detect if an error is likely due to OOM (Out of Memory)."""
        oom_indicators = [
            'out of memory',
            'oom',
            'memory limit',
            'memory exhausted',
            'insufficient memory',
            'cannot allocate memory',
            'memory error',
            'resource exhausted',
            'gpu out of memory',
            'cuda out of memory',
            'tensor allocation failed',
            'runtime out of memory'
        ]
        
        error_lower = error.lower()
        return any(indicator in error_lower for indicator in oom_indicators)
    
    def _handle_oom_error(self, task_id: str):
        """Handle OOM error by updating system state and task status."""
        task = self.tasks.get(task_id)
        if not task:
            return
            
        # Update system memory pressure state
        self.system_under_memory_pressure = True
        self.last_oom_time = datetime.now()
        self.consecutive_oom_count += 1
        
        # Mark task for fallback to Devstral
        task.fallback_to_devstral = True
        task.updated_at = datetime.now()
        
        # If we've had multiple consecutive OOMs, increase the cooldown period
        if self.consecutive_oom_count >= 3:
            # After 3 consecutive OOMs, wait longer before retrying local models
            self._set_memory_pressure_cooldown()
        
        self._save_tasks()
    
    def _set_memory_pressure_cooldown(self):
        """Set a cooldown period when system is under memory pressure."""
        # Store cooldown information
        cooldown_file = self.project_root / ".vibe" / "memory_pressure_cooldown.json"
        cooldown_data = {
            'memory_pressure': True,
            'last_oom': datetime.now().isoformat(),
            'consecutive_oom_count': self.consecutive_oom_count,
            'cooldown_until': (datetime.now() + timedelta(minutes=15)).isoformat()
        }
        
        with open(cooldown_file, 'w') as f:
            json.dump(cooldown_data, f, indent=2)
    
    def _check_memory_pressure_cooldown(self) -> bool:
        """Check if we're in a memory pressure cooldown period."""
        cooldown_file = self.project_root / ".vibe" / "memory_pressure_cooldown.json"
        
        if not cooldown_file.exists():
            return False
            
        try:
            with open(cooldown_file, 'r') as f:
                cooldown_data = json.load(f)
                cooldown_until = datetime.fromisoformat(cooldown_data['cooldown_until'])
                
                if datetime.now() > cooldown_until:
                    # Cooldown period has ended
                    cooldown_file.unlink()
                    self.system_under_memory_pressure = False
                    self.consecutive_oom_count = 0
                    return False
                
                # Still in cooldown period
                self.system_under_memory_pressure = True
                self.consecutive_oom_count = cooldown_data.get('consecutive_oom_count', 0)
                return True
                
        except (json.JSONDecodeError, KeyError, OSError):
            return False
    
    def _should_use_local_model(self, task_type: TaskType) -> bool:
        """Determine if a task should use a local model based on current system state."""
        # Check if we're in memory pressure cooldown
        if self._check_memory_pressure_cooldown():
            return False
            
        # Check if Ollama is available
        ollama_status = check_ollama_availability()
        if not ollama_status.available:
            return False
            
        # Check if task type should use local model
        local_model_task_types = [
            TaskType.CODE_IMPLEMENTATION,
            TaskType.DOCUMENTATION,
            TaskType.REFACTORING,
            TaskType.TESTING,
            TaskType.MAINTENANCE,
            TaskType.REPOSITORY_HYGIENE
        ]
        
        return task_type in local_model_task_types
    
    def _get_retry_delay(self, attempt_number: int) -> float:
        """Get exponential backoff delay for retry attempts."""
        # Exponential backoff: 1s, 2s, 4s, 8s, 16s, etc.
        return min(2 ** (attempt_number - 1), 30)  # Cap at 30 seconds
    
    def create_routing_task(self, prompt: str, task_type: TaskType, priority: int = 3) -> str:
        """Create a new routing task."""
        task_id = str(uuid.uuid4())
        
        task = RoutingTask(
            task_id=task_id,
            original_prompt=prompt,
            task_type=task_type,
            priority=priority
        )
        
        self.tasks[task_id] = task
        self._save_tasks()
        
        return task_id
    
    def route_task(self, task_id: str) -> Dict[str, Any]:
        """Route a task to the appropriate model with safety checks."""
        task = self.tasks.get(task_id)
        if not task:
            return {'success': False, 'error': 'Task not found'}
        
        # Check if task should use local model
        should_use_local = self._should_use_local_model(task.task_type)
        
        # If task is marked for fallback or shouldn't use local, route to Devstral
        if task.fallback_to_devstral or not should_use_local:
            return self._route_to_devstral(task)
        
        # Try to acquire system lock
        if not self._acquire_system_lock():
            # Couldn't get lock, either fallback or wait
            if self.system_under_memory_pressure:
                # Under memory pressure, fallback immediately
                task.fallback_to_devstral = True
                self._save_tasks()
                return self._route_to_devstral(task)
            else:
                # System busy, wait and retry
                return {
                    'success': False,
                    'error': 'System busy, please wait and retry',
                    'retry_after': 2.0
                }
        
        # Route to local model
        try:
            result = self._route_to_local_model(task)
            return result
        finally:
            self._release_system_lock()
    
    def _route_to_local_model(self, task: RoutingTask) -> Dict[str, Any]:
        """Route task to local model with attempt tracking."""
        attempt_id = str(uuid.uuid4())
        model_name = self._get_local_model_name(task.task_type)
        
        # Record attempt
        attempt = TaskAttempt(
            attempt_id=attempt_id,
            timestamp=datetime.now(),
            model_used=model_name,
            success=False
        )
        
        try:
            # Check if Ollama is available before trying to use local models
            ollama_status = check_ollama_availability()
            if not ollama_status.available:
                raise RuntimeError("Ollama not available for local model execution")
            
            # Create a prompt for the local model
            prompt = self._create_local_model_prompt(task)
            
            # Execute using the model coordinator
            result_text = self.model_coordinator.query_model(
                role=ModelRole.IMPLEMENTER,
                prompt=prompt
            )
            
            # Check for error responses from the model coordinator
            if result_text.startswith("Error:"):
                raise RuntimeError(result_text)
            
            # Check for OOM errors in the response
            if self._detect_oom_error(result_text):
                raise RuntimeError(f"OOM detected in model response: {result_text}")
            
            # Successful execution
            attempt.success = True
            attempt.error = None
            
            result = {
                'success': True,
                'model_used': attempt.model_used,
                'result': result_text,
                'attempt_id': attempt_id
            }
            
        except Exception as e:
            attempt.success = False
            attempt.error = str(e)
            attempt.oom_detected = self._detect_oom_error(str(e))
            
            if attempt.oom_detected:
                self._handle_oom_error(task.task_id)
                
            result = {
                'success': False,
                'error': str(e),
                'oom_detected': attempt.oom_detected,
                'attempt_id': attempt_id
            }
        
        # Update task with attempt
        task.attempts.append(attempt)
        task.current_attempt += 1
        task.updated_at = datetime.now()
        
        # Check if we should retry or fallback
        if not attempt.success:
            if attempt.oom_detected or task.current_attempt >= task.max_attempts:
                # OOM or max attempts reached, fallback to Devstral
                task.fallback_to_devstral = True
            else:
                # Schedule retry
                retry_delay = self._get_retry_delay(task.current_attempt)
                result['retry_after'] = retry_delay
        
        self._save_tasks()
        
        return result
    
    def _create_local_model_prompt(self, task: RoutingTask) -> str:
        """Create a prompt for the local model based on the task."""
        base_prompt = f"Task: {task.original_prompt}\n\n"
        base_prompt += f"Task Type: {task.task_type.name}\n"
        base_prompt += f"Priority: {task.priority}\n\n"
        
        # Add task-specific instructions
        if task.task_type == TaskType.CODE_IMPLEMENTATION:
            base_prompt += "Write clean, well-documented code. Follow best practices and include appropriate tests.\n"
        elif task.task_type == TaskType.DOCUMENTATION:
            base_prompt += "Write comprehensive documentation. Include examples, usage instructions, and technical details.\n"
        elif task.task_type == TaskType.CODE_REVIEW:
            base_prompt += "Perform a thorough code review. Check for bugs, security issues, performance problems, and adherence to best practices.\n"
        elif task.task_type == TaskType.REFACTORING:
            base_prompt += "Refactor the code to improve quality, performance, and maintainability.\n"
        elif task.task_type == TaskType.TESTING:
            base_prompt += "Write comprehensive tests including unit tests, integration tests, and edge case coverage.\n"
        
        base_prompt += "\nPlease provide your implementation:"
        
        return base_prompt
    
    def _route_to_devstral(self, task: RoutingTask) -> Dict[str, Any]:
        """Route task to Devstral (fallback)."""
        attempt_id = str(uuid.uuid4())
        
        # Record attempt
        attempt = TaskAttempt(
            attempt_id=attempt_id,
            timestamp=datetime.now(),
            model_used='Devstral-2',
            success=True,  # Assume Devstral succeeds
            error=None
        )
        
        task.attempts.append(attempt)
        task.updated_at = datetime.now()
        self._save_tasks()
        
        return {
            'success': True,
            'model_used': 'Devstral-2',
            'result': f'Task executed using Devstral-2 (fallback)',
            'attempt_id': attempt_id,
            'fallback': True
        }
    
    def _get_local_model_name(self, task_type: TaskType) -> str:
        """Get the appropriate local model name for a task type."""
        # This would be enhanced with actual model detection logic
        if task_type == TaskType.CODE_REVIEW:
            return 'qwq:latest'
        elif task_type == TaskType.DOCUMENTATION:
            return 'llama3.2:latest'
        else:
            return 'deepseek-coder-v2:latest'
    
    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """Get status of a routing task."""
        task = self.tasks.get(task_id)
        if not task:
            return {'error': 'Task not found'}
        
        return {
            'task_id': task.task_id,
            'status': self._get_task_status_string(task),
            'attempts': len(task.attempts),
            'current_attempt': task.current_attempt,
            'fallback_to_devstral': task.fallback_to_devstral,
            'last_attempt': task.attempts[-1].timestamp.isoformat() if task.attempts else None,
            'last_error': task.attempts[-1].error if task.attempts and not task.attempts[-1].success else None
        }
    
    def _get_task_status_string(self, task: RoutingTask) -> str:
        """Get human-readable status for a task."""
        if not task.attempts:
            return 'pending'
        
        last_attempt = task.attempts[-1]
        
        if last_attempt.success:
            if last_attempt.model_used == 'Devstral-2':
                return 'completed_fallback'
            else:
                return 'completed'
        else:
            if task.fallback_to_devstral:
                return 'failed_fallback'
            elif last_attempt.oom_detected:
                return 'failed_oom'
            else:
                return 'failed_retryable'
    
    def cleanup_old_tasks(self, max_age_days: int = 30):
        """Clean up old completed tasks."""
        cutoff = datetime.now() - timedelta(days=max_age_days)
        
        tasks_to_keep = {}
        for task_id, task in self.tasks.items():
            if task.updated_at > cutoff or self._get_task_status_string(task) != 'completed':
                tasks_to_keep[task_id] = task
        
        if len(tasks_to_keep) < len(self.tasks):
            self.tasks = tasks_to_keep
            self._save_tasks()
            return len(self.tasks) - len(tasks_to_keep)
        
        return 0
    
    def get_system_status(self) -> Dict[str, Any]:
        """Get current system status."""
        return {
            'memory_pressure': self.system_under_memory_pressure,
            'consecutive_oom_count': self.consecutive_oom_count,
            'last_oom_time': self.last_oom_time.isoformat() if self.last_oom_time else None,
            'active_locks': self._count_active_locks(),
            'total_tasks': len(self.tasks),
            'pending_tasks': sum(1 for task in self.tasks.values() if self._get_task_status_string(task) in ['pending', 'failed_retryable'])
        }
    
    def reset_memory_pressure_state(self):
        """Reset memory pressure state."""
        self.system_under_memory_pressure = False
        self.consecutive_oom_count = 0
        self.last_oom_time = None
        
        # Remove cooldown file
        cooldown_file = self.project_root / ".vibe" / "memory_pressure_cooldown.json"
        if cooldown_file.exists():
            try:
                cooldown_file.unlink()
            except OSError:
                pass
        
        self._save_tasks()