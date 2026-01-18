# Vibe Collaborative Framework

## Overview

The Porker-Vibe Collaborative Framework extends Mistral Vibe to support sophisticated dual-model collaboration. By leveraging specialized models for specific tasks, we achieve higher quality code generation, better architecture, and more robust documentation.

**Core Collaboration Pair:**
- **Devstral-2 (Planning & Architecture):** Handles high-level strategy, system design, code review, and user interaction.
- **Deepseek-Coder-v2 (Implementation & Execution):** Handles low-level implementation, comprehensive testing, documentation, and repository maintenance.

## Architecture

The system operates through a coordinated agent workflow:

1.  **CollaborativeAgent:** The orchestrator that manages the project lifecycle.
2.  **ModelCoordinator:** The bridge between Devstral and local models, managing context and routing.
3.  **TaskManager:** The scheduler that breaks down high-level goals into executable units.

## Task Types and routing

The framework intelligently routes work based on the nature of the task:

| Task Type | Assigned Model | Focus Area |
|-----------|---------------|------------|
| **PLANNING** | Devstral-2 | Project strategy, requirements analysis |
| **ARCHITECTURE** | Devstral-2 | System design, pattern selection |
| **CODE_REVIEW** | Devstral-2 | Security auditing, logic verification |
| **CODE_IMPLEMENTATION** | Deepseek-Coder-v2 | Writing functional, clean code |
| **DOCUMENTATION** | Deepseek-Coder-v2 | API references, docstrings, READMEs |
| **REFACTORING** | Deepseek-Coder-v2 | Code optimization, technical debt reduction |
| **TESTING** | Deepseek-Coder-v2 | Unit, integration, and regression tests |
| **MAINTENANCE** | Deepseek-Coder-v2 | Dependency management, linting fixes |

## Workflow Lifecycle

1.  **Project Initialization:** You describe the goal.
2.  **Strategic Planning:** Devstral-2 analyzes the requirements and outlines a development roadmap.
3.  **Task Decomposition:** The roadmap is converted into atomic, executable tasks.
4.  **Intelligent Assignment:** Tasks are routed to the model best suited for execution.
5.  **Execution & Implementation:** Specialized models perform the work (coding, documenting, etc.).
6.  **Review & Quality Assurance:** Devstral-2 reviews the output against the original plan.
7.  **Iterative Refinement:** The cycle continues until all success criteria are met.

## Setup

### Requirements

- Python 3.8+
- Mistral Vibe
- **Ollama** (for running local models)
- Local models pulled via Ollama (e.g., `deepseek-coder-v2`, `qwq`, `llama3.2`)

### Configuration

The framework is auto-configuring but highly customizable. By default, it looks for models on `http://localhost:11434`.

**Default Behavior:**
If `VIBE_LOCAL_MODEL` is detected, the framework automatically spins up a background Ollama instance (if not already running) and links the models.

## Usage

### programmatic Usage

You can use the framework directly in your Python scripts to build custom workflows:

```python
from pathlib import Path
from vibe.collaborative import CollaborativeAgent, TaskType, ModelRole

# Initialize agent
agent = CollaborativeAgent(Path("./my-project"))

# Start a new project
agent.start_project(
    project_name="Intelligent Task Manager",
    project_description="A Python-based CLI tool for managing daily tasks with AI priority sorting."
)

# The agent now autonomously manages the lifecycle
while True:
    result = agent.execute_next_task()
    if result['status'] == 'no_tasks':
        break
    print(f"Executed: {result['task_id']}")
```

### Advanced Customization

You can inject custom tasks into the queue at any time:

```python
# Force a high-priority security audit
agent.add_custom_task(
    task_type=TaskType.CODE_REVIEW,
    description="Audit the authentication module for potential SQL injection vulnerabilities.",
    priority=1
)
```

## Best Practices

-   **Detailed Prompts:** The quality of the plan depends on the clarity of your initial project description.
-   **Specialized Models:** For best results, use `deepseek-coder-v2` for code and `llama3.2` for documentation.
-   **Review Cycles:** Allow the Review model (Devstral or `qwq`) to critique implementation before finalizing.

## Support

For issues, please open a ticket in the main repository.
