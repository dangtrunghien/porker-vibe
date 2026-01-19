# Vibe Collaborative Framework

A forked version of Mistral Vibe that integrates Devstral-2 with local models via Ollama for collaborative coding, enhanced with intelligent planning, todo tracking, and a refined TUI.

*Please report issues on this Github and not the main mistralai/mistral-vibe repo.*

## Features

### Core Capabilities
- **Fully Local Mode**: Run entirely on your PC without Mistral API (set VIBE_PLANNING_MODEL)
- **Hybrid Mode**: Devstral for planning, local models for implementation (default)
- **Multi-Model Collaboration**: Route tasks to specialized models automatically
- **Automatic Ollama Management**: Vibe automatically starts Ollama if needed and stops it on exit
- **Fallback Behavior**: Gracefully falls back to standard Vibe when Ollama isn't available

### Enhanced Planning & Tracking
- **Todo System**: Agents track multi-step tasks in real-time with `TodoWrite` tool
- **PLAN.md Integration**: High-level project planning that guides agent work across sessions
- **PlanSync Tool**: Agents synchronize immediate work (todos) with long-term goals (PLAN.md)
- **Persistent State**: Todos and plans persist per-project in `.vibe/` directory
- **Real-Time TUI Updates**: Watch agent progress with live todo status in the terminal UI

### Developer Experience
- **Enhanced TUI**: Redesigned with "complex simplicity" - sophisticated visual structure through clean patterns
- **Error Detection**: Multi-level error detection with graceful degradation and recovery
- **Debug Loops**: Systematic debugging with hypothesis-driven iteration
- **Self-Verification**: Built-in quality checks and verification protocols
- **Test-First Development**: Integrated support for TDD workflow

## Operating Modes

### Fully Local Mode (No Mistral API)
```bash
export VIBE_PLANNING_MODEL="qwen2.5-coder:32b"  # Planning
export VIBE_CODE_MODEL="deepseek-coder-v2:latest"  # Code
export VIBE_REVIEW_MODEL="qwq:latest"  # Review
export VIBE_DOCS_MODEL="llama3.2:latest"  # Docs
```
All work happens locally via Ollama. No internet or API key required.

### Hybrid Mode (Recommended)
```bash
# Don't set VIBE_PLANNING_MODEL
export VIBE_CODE_MODEL="deepseek-coder-v2:latest"
export VIBE_REVIEW_MODEL="qwq:latest"
export VIBE_DOCS_MODEL="llama3.2:latest"
```
Devstral handles planning (via Mistral API), local models handle implementation.

### Single Model Mode
```bash
export VIBE_LOCAL_MODEL="deepseek-coder-v2:latest"
```
One local model handles all implementation tasks, Devstral handles planning.

## Quick Start

1. **Install Ollama** and pull specialized models:
   ```bash
   # Install Ollama (https://ollama.ai)
   curl -fsSL https://ollama.ai/install.sh | sh

   # For fully local mode (no Mistral API)
   ollama pull qwen2.5-coder:32b          # For planning
   ollama pull deepseek-coder-v2:latest   # For code
   ollama pull qwq:latest                  # For review
   ollama pull llama3.2:latest             # For docs

   # OR for hybrid mode (just pull implementation models)
   ollama pull deepseek-coder-v2:latest   # For code
   ollama pull qwq:latest                  # For review
   ollama pull llama3.2:latest             # For docs
   ```

2. **Set environment variables**:
   ```bash
   # Fully local mode (no Mistral API required)
   export VIBE_PLANNING_MODEL="qwen2.5-coder:32b"  # For planning/coordination
   export VIBE_CODE_MODEL="deepseek-coder-v2:latest"
   export VIBE_REVIEW_MODEL="qwq:latest"
   export VIBE_DOCS_MODEL="llama3.2:latest"

   # OR hybrid mode (Devstral for planning, local for implementation)
   # Don't set VIBE_PLANNING_MODEL, only set implementation models:
   export VIBE_CODE_MODEL="deepseek-coder-v2:latest"
   export VIBE_REVIEW_MODEL="qwq:latest"
   export VIBE_DOCS_MODEL="llama3.2:latest"

   # OR single model mode
   export VIBE_LOCAL_MODEL="deepseek-coder-v2:latest"
   ```

3. **Run Vibe** (Ollama starts automatically):
   ```bash
   vibe
   ```

   You'll see output indicating Ollama started successfully and collaborative mode is enabled.

   **Note**: If Ollama is already running (e.g., as a systemd service), Vibe will detect and use it without starting a new instance. When you exit Vibe, it only stops Ollama if Vibe started it.

## Architecture

### Model Roles

| Model | Role | Responsibilities | Required API |
|-------|------|------------------|--------------|
| **Planning Model** | Coordinator | Project planning, architecture design, task delegation | Mistral API (default) or Local (if VIBE_PLANNING_MODEL set) |
| **CODE Model** | Implementer | Code writing, refactoring, tests | Local (Ollama) |
| **REVIEW Model** | Reviewer | Code review, security analysis, quality assessment | Local (Ollama) |
| **DOCS Model** | Documenter | Documentation, .gitignore, project organization | Local (Ollama) |

### Task Distribution

Tasks are automatically routed to specialized models:

- **Coordinator (Devstral-2)**:
  - Planning and architecture
  - Task coordination between models
  - Strategy and decision-making
  - Answering architecture questions

- **CODE Model** (e.g., deepseek-coder-v2):
  - Code implementation
  - Refactoring and optimization
  - Writing tests

- **REVIEW Model** (e.g., qwq):
  - Code review and analysis
  - Security vulnerability detection
  - Best practices verification

- **DOCS Model** (e.g., llama3.2):
  - Documentation (README, docstrings)
  - .gitignore maintenance
  - Project folder organization
  - Git commit messages

## Environment Variables

### Single Model Mode

| Variable | Description | Default |
|----------|-------------|---------|
| VIBE_LOCAL_MODEL | Name of the Ollama model for all tasks | None (disables collaborative mode) |
| VIBE_OLLAMA_ENDPOINT | Custom Ollama API endpoint | http://localhost:11434 |

### Planning Model (Optional - for Fully Local Mode)

| Variable | Purpose | Suggested Model | Default |
|----------|---------|-----------------|---------|
| VIBE_PLANNING_MODEL | Planning and coordination (replaces Devstral) | qwen2.5-coder:32b, deepseek-r1:latest | None (uses Devstral via Mistral API) |

**Fully Local Mode:** Set VIBE_PLANNING_MODEL to run Vibe entirely locally without the Mistral API.

### Implementation Models (for Collaborative Mode)

Use specialized models for different task types:

| Variable | Purpose | Suggested Model | Default |
|----------|---------|-----------------|---------|
| VIBE_CODE_MODEL | Code writing, refactoring, tests | deepseek-coder-v2:latest | Falls back to VIBE_LOCAL_MODEL |
| VIBE_REVIEW_MODEL | Code review and quality analysis | qwq:latest | Falls back to VIBE_LOCAL_MODEL |
| VIBE_DOCS_MODEL | Documentation, git, cleanup | llama3.2:latest | Falls back to VIBE_LOCAL_MODEL |

**Note:** Ollama loads models on-demand, so you can have multiple models configured without loading them all at once.

## Usage Examples

### Basic Usage (Auto-Detection)

```bash
# Set your local model
export VIBE_LOCAL_MODEL="deepseek-coder-v2:latest"

# Run Vibe - collaborative mode auto-enables
vibe
```

### Manual Collaborative Mode

```bash
# Force collaborative mode (even without env var)
vibe --collaborative
```

### Multi-Model Setup (Recommended)

```bash
# Set up specialized models for different tasks
export VIBE_CODE_MODEL="deepseek-coder-v2:latest"     # For code implementation
export VIBE_REVIEW_MODEL="qwq:latest"                  # For code review
export VIBE_DOCS_MODEL="llama3.2:latest"               # For documentation

# Pull the models (one-time setup)
ollama pull deepseek-coder-v2:latest
ollama pull qwq:latest
ollama pull llama3.2:latest

# Run Vibe - models auto-route by task type
vibe
```

### Single Model Mode

```bash
# Use one model for everything
export VIBE_LOCAL_MODEL="deepseek-coder-v2:latest"
vibe

# Or use different single models
export VIBE_LOCAL_MODEL="codellama:latest"
vibe
```

### Custom Ollama Endpoint

```bash
# Remote Ollama server
export VIBE_OLLAMA_ENDPOINT="http://192.168.1.100:11434"
export VIBE_LOCAL_MODEL="deepseek-coder-v2:latest"
vibe
```

## Agent Tools & Capabilities

Vibe agents have access to powerful tools for planning and execution:

### TodoWrite Tool
- Track multi-step tasks with status (pending, in_progress, completed)
- Display real-time progress in the TUI
- Persist todos per-project in `.vibe/todos.json`
- Agents use this for complex tasks requiring multiple steps

Example agent workflow:
```markdown
1. Create todos using TodoWrite
2. Mark task as in_progress before starting work
3. Mark completed immediately after finishing
4. Update todos when discovering new requirements
```

### PlanSync Tool
- Read project's PLAN.md to understand goals and architecture
- Extract "Next Steps" from PLAN.md to create new todos
- Keep immediate work aligned with long-term project vision
- Sync work across sessions with persistent planning

### Planning System
- **PLAN.md**: High-level project planning document (auto-created, .gitignored)
- **PlanManager**: Hierarchical planning (Goal → Epics → Tasks → Subtasks)
- **TodoManager**: Session-scoped immediate task tracking
- **Automatic Sync**: Agents check PLAN.md when todos complete

### Enhanced TUI Features
- **Live Todo Display**: See current tasks at the top of the interface
- **Status Icons**: ✓ (completed), ▶ (in_progress), ○ (pending)
- **Visual Hierarchy**: Color-coded borders and spacing for clarity
- **Tool Call Tracking**: Watch agents use tools in real-time
- **Reasoning Display**: Optional display of agent thinking process

## Workflow

### Basic Workflow
1. **Devstral-2 analyzes** requirements and creates a development plan
2. **Tasks are distributed** to the local model for implementation
3. **Local model writes** code, documentation, and maintains the repo
4. **Devstral-2 reviews** and provides feedback
5. **Iterative refinement** until completion

### Enhanced Workflow with Planning
1. **Agent reads PLAN.md** to understand project goals
2. **Creates todos** using TodoWrite based on next steps
3. **Marks task as in_progress** before starting work
4. **Implements features** with systematic debugging
5. **Marks completed** and moves to next todo
6. **When all todos complete**, uses PlanSync to get next steps from PLAN.md
7. **Updates PLAN.md** as project evolves

## Fallback Behavior

When Ollama isn't running or VIBE_LOCAL_MODEL isn't set, Vibe continues to work normally using Devstral-2 for everything.

## Project Structure

```
vibe/
├── .vibe/                  # Project-specific state (auto-created, .gitignored)
│   ├── todos.json          # Persistent todo tracking
│   ├── plans/              # Structured plan data
│   └── collaborative_router.lock  # Multi-instance safety
├── PLAN.md                 # High-level project plan (auto-created, .gitignored)
├── AGENTS.md               # Agent behavior guidelines (Python 3.12+ best practices)
├── vibe/
│   ├── core/               # Core agent logic
│   │   ├── agent.py        # Main agent implementation
│   │   ├── todo_manager.py # Todo tracking system
│   │   ├── plan_manager.py # Hierarchical planning
│   │   └── plan_document_manager.py  # PLAN.md management
│   ├── cli/
│   │   └── textual_ui/     # Terminal UI
│   ├── collaborative/      # Multi-model coordination
│   └── core/tools/builtins/
│       ├── todo_write.py   # TodoWrite tool
│       └── plan_sync.py    # PlanSync tool
```

## Agent Guidelines (AGENTS.md)

The `AGENTS.md` file contains comprehensive guidelines for agent behavior:

- **Modern Python 3.12+ practices** (match-case, walrus operator, type hints)
- **Complex task decomposition** strategies
- **Debug loops and iterative refinement** protocols
- **Error detection and handling** at multiple levels
- **Test-driven development** workflow
- **Self-verification checklists** before task completion
- **Planning and project management** best practices
- **Handling uncertainty** - when to ask vs. when to decide

These guidelines ensure agents handle complex, multi-file coding tasks with robust error detection and systematic debugging.

## Setup Requirements

- **Python 3.12+** (required for modern syntax features)
- **Ollama** running locally (or accessible endpoint)
- **Mistral API key** - Only required if NOT using VIBE_PLANNING_MODEL (fully local mode)
- **Local models** pulled in Ollama
- **uv** package manager (recommended for Arch Linux users)

## Installation

### Using uv (Recommended)

The project uses `uv` for Python environment management (see `AGENTS.md` for rationale):

```bash
# Install uv (if not installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone the repository
git clone https://github.com/your-username/vibe.git
cd vibe

# Install dependencies
uv sync

# Run Vibe
uv run vibe

# Or install in development mode
uv pip install -e .
```

**Why uv?**
- Faster than pip
- Better dependency resolution
- Avoids environment drift
- Modern Python packaging best practices
- Required by `AGENTS.md` guidelines

### Traditional Installation (Linux / macOS)

```bash
# Clone the repository
git clone https://github.com/your-username/vibe.git
cd vibe

# Install in development mode
pip install -e .

# Or install normally
pip install .

# Run Vibe
vibe
```

**Note:** If using traditional installation, agents in this fork follow `uv` conventions. Some agent-generated commands may use `uv run` syntax.

## Using Planning Features

### Creating a PLAN.md

When starting a new project or complex feature:

```bash
# Run vibe and create PLAN.md
vibe

# The agent will create PLAN.md with this structure:
```

```markdown
# Project Plan

## Current Status
Work in progress.

## Architecture
Key design decisions and patterns.

## Milestones
- [ ] Milestone 1: Description
- [x] Milestone 2: Completed milestone

## Current Blockers
Any issues preventing progress.

## Next Steps
1. Specific actionable task
2. Another task
```

### Working with Todos

Agents automatically use todos for complex tasks:

```
User: "Implement user authentication with JWT tokens"

Agent: Creates todos:
  ○ Research JWT implementation patterns
  ○ Create authentication middleware
  ○ Implement login endpoint
  ○ Implement token verification
  ○ Add tests for auth flow
  ○ Update documentation

Agent marks first todo as in progress:
  ▶ Researching JWT implementation patterns
  ○ Create authentication middleware
  ... (rest pending)

Agent completes first todo:
  ✓ Research JWT implementation patterns
  ▶ Creating authentication middleware
  ... (continues through list)
```

### Syncing Todos with PLAN.md

When all todos are complete:

```
Agent uses PlanSync tool:
  1. Reads PLAN.md
  2. Extracts "Next Steps" section
  3. Creates new todos based on next steps
  4. Continues work aligned with project plan
```

### Best Practices

1. **Keep PLAN.md updated** - Update as architecture evolves
2. **Use todos for session work** - Track immediate multi-step tasks
3. **Use PLAN.md for project scope** - High-level goals and milestones
4. **Let agents sync** - Agents use PlanSync to stay aligned
5. **Review .vibe/** - Contains persistent state (todos, plans, locks)

## Troubleshooting

### "Ollama is not running" or "Failed to start Ollama"

Vibe tries to start Ollama automatically. If it fails:

```bash
# Check if Ollama is installed
which ollama

# If not installed, install it:
curl -fsSL https://ollama.ai/install.sh | sh

# You can also run Ollama as a systemd service (optional)
sudo systemctl start ollama
sudo systemctl enable ollama  # Auto-start on boot
```

If Ollama is running as a systemd service, Vibe will detect it and won't start a duplicate instance.

### "Model not found"
```bash
# Pull the model first
ollama pull deepseek-coder-v2:latest

# Verify it's available
ollama list
```

### How does Ollama handle multiple models?

Ollama loads models **on-demand** when you make a request. You don't need to worry about memory - only the currently-used model is loaded. When you switch tasks (e.g., from code to review), Ollama automatically swaps models.

### Do I need a Mistral API key?

- **Fully Local Mode** (VIBE_PLANNING_MODEL set): No API key needed
- **Hybrid/Single Model Mode** (default): Yes, you need a Mistral API key for Devstral

To set your API key:
```bash
export MISTRAL_API_KEY="your-api-key"
# Or add to ~/.vibe/.env
```

Get a key at: https://console.mistral.ai/

### Connection Timeout
```bash
# Check if Ollama is listening
curl http://localhost:11434/api/tags
```

### Creating Custom Models

You can create custom models with `ollama create`:

```bash
# Create a custom model with a Modelfile
ollama create gkm-4.7 -f ./Modelfile

# Then use it
export VIBE_REVIEW_MODEL="gkm-4.7"
```

See [Ollama Modelfile documentation](https://github.com/ollama/ollama/blob/main/docs/modelfile.md) for more info.

### Todos not showing in TUI?

Check that:
1. The agent has created todos using `TodoWrite` tool
2. The `.vibe/` directory exists in your project
3. The TodoWidget is not collapsed (press Ctrl+T to toggle)

To verify todos exist:
```bash
cat .vibe/todos.json
```

### Want to see agent reasoning?

The TUI shows agent thinking process (when available). Look for the collapsible reasoning sections marked with "Reasoning:" header.

## FAQ

**Q: Do I need a Mistral API key if I set VIBE_PLANNING_MODEL?**
A: No! Setting `VIBE_PLANNING_MODEL` enables fully local mode - no API key needed.

**Q: What's the difference between PlanManager and PLAN.md?**
A:
- **PlanManager**: Structured hierarchical data (Goal → Epics → Tasks → Subtasks) stored in `.vibe/plans/`
- **PLAN.md**: Human-readable markdown document with goals, architecture, and next steps

Both work together. Agents can use either depending on the task.

**Q: Will todos persist across vibe sessions?**
A: Yes! Todos are saved to `.vibe/todos.json` per-project. They persist until explicitly cleared or all marked complete.

**Q: Can I manually edit PLAN.md?**
A: Absolutely! PLAN.md is meant to be human-editable. Update it anytime and agents will read the latest version.

**Q: How do agents decide when to use todos vs. direct implementation?**
A: Agents use the `TodoWrite` tool for complex multi-step tasks (typically 3+ steps). For simple single-step tasks, they work directly.

**Q: What are the .vibe/ files for?**
A:
- `todos.json` - Persistent todo tracking
- `plans/` - Structured hierarchical plans
- `collaborative_router.lock` - Multi-instance safety for collaborative mode
- Other session/state files

**Q: Can I use this without the TUI?**
A: Yes! Run `vibe -c "your command"` for non-interactive mode. Todos still persist to `.vibe/todos.json`.

**Q: How does the enhanced error detection work?**
A: Agents follow guidelines in `AGENTS.md` for:
- Input validation at entry points
- Type safety with Pydantic
- Graceful error recovery with retry logic
- Systematic debugging with hypothesis testing
- Compilation checks after edits

## License

See the original Vibe repository for license information.

## Contributing

This is a personal fork with experimental features. For the official Mistral Vibe project, see: https://github.com/mistralai/mistral-vibe

Contributions welcome! Please note:
- Follow guidelines in `AGENTS.md` for code style
- Test with both local and hybrid modes
- Ensure backwards compatibility with standard Vibe
- Add tests for new features
