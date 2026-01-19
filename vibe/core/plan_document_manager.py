"""
Plan Document Manager for PLAN.md

Manages the project's PLAN.md file which contains high-level goals,
milestones, architecture decisions, and next steps.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional


class PlanDocumentManager:
    """
    Manages PLAN.md - a markdown file containing the project's high-level plan.

    This is different from PlanManager which handles structured hierarchical plans.
    PLAN.md is a human-readable document that guides the agent's work.
    """

    def __init__(self, project_path: Path):
        self.project_path = project_path
        self._plan_file_path = project_path / "PLAN.md"

    @property
    def exists(self) -> bool:
        """Check if PLAN.md exists."""
        return self._plan_file_path.exists()

    def read(self) -> Optional[str]:
        """Read the contents of PLAN.md."""
        if not self.exists:
            return None

        try:
            return self._plan_file_path.read_text(encoding="utf-8")
        except (FileNotFoundError, IOError):
            return None

    def write(self, content: str) -> None:
        """Write content to PLAN.md."""
        self._plan_file_path.write_text(content, encoding="utf-8")

    def ensure_initialized(self) -> None:
        """Ensure PLAN.md exists with a basic template if it doesn't."""
        if self.exists:
            return

        template = """# Project Plan

## Current Status
Work in progress.

## Architecture
To be documented.

## Milestones
- [ ] Initial setup

## Current Blockers
None.

## Next Steps
1. Define project goals
2. Create initial architecture
"""
        self.write(template)

    def extract_next_steps(self) -> list[str]:
        """
        Extract the "Next Steps" section from PLAN.md.
        Returns a list of step descriptions.
        """
        content = self.read()
        if not content:
            return []

        # Find the "Next Steps" section
        lines = content.split("\n")
        in_next_steps = False
        steps = []

        for line in lines:
            line_stripped = line.strip()

            # Check if we're entering the Next Steps section
            if line_stripped.startswith("## Next Steps"):
                in_next_steps = True
                continue

            # Check if we're entering a new section (exit Next Steps)
            if in_next_steps and line_stripped.startswith("##"):
                break

            # Extract numbered or bulleted list items
            if in_next_steps:
                # Match patterns like:
                # - [x] Task
                # - [ ] Task
                # 1. Task
                # - Task
                if line_stripped.startswith(("-", "*", "1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.")):
                    # Remove list markers and checkboxes
                    step = line_stripped
                    # Remove markdown checkbox
                    if "[ ]" in step or "[x]" in step:
                        step = step.replace("[ ]", "").replace("[x]", "")
                    # Remove list markers
                    for marker in ["-", "*", "1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9."]:
                        if step.startswith(marker):
                            step = step[len(marker):].strip()
                            break

                    if step:
                        steps.append(step)

        return steps
