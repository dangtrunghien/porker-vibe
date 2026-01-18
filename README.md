# Vibe Collaborative Framework

A forked version of Mistral Vibe that integrates Devstral-2 with a local model via Ollama for collaborative coding.

*Please report issues on this Github and not the main mistralai/mistral-vibe repo.*

## Features

- **Fully Local Mode**: Run entirely on your PC without Mistral API (set VIBE_PLANNING_MODEL)
- **Hybrid Mode**: Devstral for planning, local models for implementation (default)
- **Multi-Model Collaboration**: Route tasks to specialized models automatically
- **Automatic Ollama Management**: Vibe automatically starts Ollama if needed and stops it on exit
- **Fallback Behavior**: Gracefully falls back to standard Vibe when Ollama isn't available

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

## Workflow

1. **Devstral-2 analyzes** requirements and creates a development plan
2. **Tasks are distributed** to the local model for implementation
3. **Local model writes** code, documentation, and maintains the repo
4. **Devstral-2 reviews** and provides feedback
5. **Iterative refinement** until completion

## Fallback Behavior

When Ollama isn't running or VIBE_LOCAL_MODEL isn't set, Vibe continues to work normally using Devstral-2 for everything.

## Setup Requirements

- **Python 3.12+**
- **Ollama** running locally (or accessible endpoint)
- **Mistral API key** - Only required if NOT using VIBE_PLANNING_MODEL (fully local mode)
- **Local models** pulled in Ollama

## Installation

### Linux / macOS

```bash
# Clone the repository
git clone https://github.com/your-repo/vibe.git
cd vibe

# Install in development mode
pip install -e .

# Or install normally
pip install .
```

### Using uv (Recommended for Arch users)

```bash
# Install uv (if not installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install Vibe
cd /path/to/vibe
uv venv
uv pip install -e .

# Run with uv
uv run vibe
```

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

## License

See the original Vibe repository for license information.
