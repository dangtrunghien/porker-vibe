# python312.rule
# Rule for enforcing modern Python 3.12+ best practices.
# Applies to all Python files (*.py) in the project.
#
# Guidelines covered:
# - Use match-case syntax instead of if/elif/else for pattern matching.
# - Use the walrus operator (:=) when it simplifies assignments and tests.
# - Favor a "never nester" approach by avoiding deep nesting with early returns or guard clauses.
# - Employ modern type hints using built-in generics (list, dict) and the union pipe (|) operator,
#   rather than deprecated types from the typing module (e.g., Optional, Union, Dict, List).
# - Ensure code adheres to strong static typing practices compatible with static analyzers like pyright.
# - Favor pathlib.Path methods for file system operations over older os.path functions.
# - Write code in a declarative and minimalist style that clearly expresses its intent.
# - Additional best practices including f-string formatting, comprehensions, context managers, and overall PEP 8 compliance.

description: "Modern Python 3.12+ best practices and style guidelines for coding."
files: "**/*.py"

guidelines:
  - title: "Match-Case Syntax"
    description: >
      Prefer using the match-case construct over traditional if/elif/else chains when pattern matching
      is applicable. This leads to clearer, more concise, and more maintainable code.

  - title: "Walrus Operator"
    description: >
      Utilize the walrus operator (:=) to streamline code where assignment and conditional testing can be combined.
      Use it judiciously when it improves readability and reduces redundancy.

  - title: "Never Nester"
    description: >
      Aim to keep code flat by avoiding deep nesting. Use early returns, guard clauses, and refactoring to
      minimize nested structures, making your code more readable and maintainable.

  - title: "Modern Type Hints"
    description: >
      Adopt modern type hinting by using built-in generics like list and dict, along with the pipe (|) operator
      for union types (e.g., int | None). Avoid older, deprecated constructs such as Optional, Union, Dict, and List
      from the typing module.

  - title: "Strong Static Typing"
    description: >
      Write code with explicit and robust type annotations that are fully compatible with static type checkers
      like pyright. This ensures higher code reliability and easier maintenance.

  - title: "Pydantic-First Parsing"
    description: >
      Prefer Pydantic v2's native validation over ad-hoc parsing. Use `model_validate`,
      `field_validator`, `from_attributes`, and field aliases to coerce external SDK/DTO objects.
      Avoid manual `getattr`/`hasattr` flows and custom constructors like `from_sdk` unless they are
      thin wrappers over `model_validate`. Keep normalization logic inside model validators so call sites
      remain declarative and typed.

  - title: "Pathlib for File Operations"
    description: >
      Favor the use of pathlib.Path methods for file system operations. This approach offers a more
      readable, object-oriented way to handle file paths and enhances cross-platform compatibility,
      reducing reliance on legacy os.path functions.

  - title: "Declarative and Minimalist Code"
    description: >
      Write code that is declarative—clearly expressing its intentions rather than focusing on implementation details.
      Strive to keep your code minimalist by removing unnecessary complexity and boilerplate. This approach improves
      readability, maintainability, and aligns with modern Python practices.

  - title: "Additional Best Practices"
    description: >
      Embrace other modern Python idioms such as:
      - Using f-strings for string formatting.
      - Favoring comprehensions for building lists and dictionaries.
      - Employing context managers (with statements) for resource management.
      - Following PEP 8 guidelines to maintain overall code style consistency.

  - title: "Exception Documentation"
    description: >
      Document exceptions accurately and minimally in docstrings:
      - Only document exceptions that are explicitly raised in the function implementation
      - Remove Raises entries for exceptions that are not directly raised
      - Include all possible exceptions from explicit raise statements
      - For public APIs, document exceptions from called functions if they are allowed to propagate
      - Avoid documenting built-in exceptions that are obvious (like TypeError from type hints)
      This ensures documentation stays accurate and maintainable, avoiding the common pitfall
      of listing every possible exception that could theoretically occur.

  - title: "Modern Enum Usage"
    description: >
      Leverage Python's enum module effectively following modern practices:
      - Use StrEnum for string-based enums that need string comparison
      - Use IntEnum/IntFlag for performance-critical integer-based enums
      - Use auto() for automatic value assignment to maintain clean code
      - Always use UPPERCASE for enum members to avoid name clashes
      - Add methods to enums when behavior needs to be associated with values
      - Use @property for computed attributes rather than storing values
      - For type mixing, ensure mix-in types appear before Enum in base class sequence
      - Consider Flag/IntFlag for bit field operations
      - Use _generate_next_value_ for custom value generation
      - Implement __bool__ when enum boolean evaluation should depend on value
      This promotes type-safe constants, self-documenting code, and maintainable value sets.

  - title: "No Inline Ignores"
    description: >
      Do not use inline suppressions like `# type: ignore[...]` or `# noqa[...]` in production code.
      Instead, fix types and lint warnings at the source by:
      - Refining signatures with generics (TypeVar), Protocols, or precise return types
      - Guarding with `isinstance` checks before attribute access
      - Using `typing.cast` when control flow guarantees the type
      - Extracting small helpers to create clearer, typed boundaries
      If a suppression is truly unavoidable at an external boundary, prefer a narrow, well-typed wrapper
      over in-line ignores, and document the rationale in code comments.

  - title: "Pydantic Discriminated Unions"
    description: >
      When modeling variants with a discriminated union (e.g., on a `transport` field), do not narrow a
      field type in a subclass (e.g., overriding `transport: Literal['http']` with `Literal['streamable-http']`).
      This violates Liskov substitution and triggers type checker errors due to invariance of class attributes.
      Prefer sibling classes plus a shared mixin for common fields and helpers, and compose the union with
      `Annotated[Union[...], Field(discriminator='transport')]`.
      Example pattern:
      - Create a base with shared non-discriminator fields (e.g., `_MCPBase`).
      - Create a mixin with protocol-specific fields/methods (e.g., `_MCPHttpFields`), without a `transport`.
      - Define sibling final classes per variant (e.g., `MCPHttp`, `MCPStreamableHttp`, `MCPStdio`) that set
        `transport: Literal[...]` once in each final class.
      - Use `match` on the discriminator to narrow types at call sites.

  - title: "Use uv for All Commands"
    description: >
      We use uv to manage our python environment. You should nevery try to run a bare python commands.
      Always run commands using `uv` instead of invoking `python` or `pip` directly.
      For example, use `uv add package` and `uv run script.py` rather than `pip install package` or `python script.py`.
      This practice helps avoid environment drift and leverages modern Python packaging best practices.
      Useful uv commands are:
      - uv add/remove <package> to manage dependencies
      - uv sync to install dependencies declared in pyproject.toml and uv.lock
      - uv run script.py to run a script within the uv environment
      - uv run pytest (or any other python tool) to run the tool within the uv environment

  - title: "Complex Task Decomposition"
    description: >
      When facing complex, difficult, or multi-file coding tasks:
      - ALWAYS use the TodoWrite tool to create a task breakdown BEFORE starting implementation
      - Decompose large tasks into atomic, testable subtasks (aim for 5-15 tasks)
      - Mark tasks as in_progress BEFORE starting work (limit to ONE at a time)
      - Mark tasks as completed IMMEDIATELY after finishing
      - If a task becomes blocked or fails, create new tasks describing the resolution strategy
      - Update the todo list when discovering new requirements or edge cases
      - Never batch completions - update status in real-time as you work
      This ensures transparency, maintains focus, and prevents getting lost in complexity.

  - title: "Debug Loops and Iterative Refinement"
    description: >
      For complex implementations that require iteration:
      - After initial implementation, ALWAYS run tests/checks to verify correctness
      - If errors occur, analyze the root cause systematically (don't guess-and-check)
      - Create specific todos for each error/failure that needs fixing
      - Document your debugging hypothesis in comments before making changes
      - After each fix, re-run tests to ensure the fix worked and didn't break anything else
      - Maintain a debug journal in comments describing what was tried and why
      - If stuck after 3 attempts, step back and reconsider the approach
      - Use print debugging, logging, or debugger tools when behavior is unclear
      Example debug loop:
      1. Run test → observe failure
      2. Form hypothesis about cause
      3. Add targeted logging/assertions
      4. Make minimal fix
      5. Verify fix resolved issue
      6. Check for regressions
      7. Clean up debug code
      8. Document solution

  - title: "Error Detection and Handling Strategies"
    description: >
      Implement robust error detection at multiple levels:
      - INPUT VALIDATION: Validate all external inputs early (user input, API responses, file contents)
      - TYPE SAFETY: Use strict type hints and runtime type checking (Pydantic) for critical paths
      - ASSERTIONS: Add strategic assert statements for invariants and preconditions
      - LOGGING: Log errors with full context (stack trace, input values, system state)
      - GRACEFUL DEGRADATION: Handle errors gracefully - don't let exceptions bubble uncaught
      - ERROR RECOVERY: Implement retry logic with exponential backoff for transient failures
      - USER FEEDBACK: Provide actionable error messages (what went wrong + how to fix)
      - MONITORING: Check for common failure modes (file not found, network errors, parsing failures)
      - TESTING: Write tests specifically for error cases and edge conditions
      - COMPILATION CHECKS: Always compile/syntax-check files after significant edits
      When an error occurs in production:
      1. Capture full error context (traceback, inputs, environment)
      2. Add error to todos as "Fix: [specific error message]"
      3. Investigate root cause (not just symptoms)
      4. Implement fix with additional safeguards
      5. Add test case to prevent regression
      6. Update error handling if needed

  - title: "Test-Driven and Verification-First Development"
    description: >
      For complex features and critical code paths:
      - Write tests BEFORE or alongside implementation (TDD when practical)
      - For bug fixes, write a failing test that reproduces the bug first
      - Run tests frequently during development (after each significant change)
      - Use pytest for unit tests, integration tests, and end-to-end tests
      - Verify code compiles/syntax-checks after every significant edit
      - Use type checkers (pyright, mypy) to catch type errors early
      - Run linters (ruff) to maintain code quality
      - For CLI tools, test both success and failure paths
      - For API integrations, test error responses and edge cases
      - Document test strategy in docstrings or comments
      Verification checklist for complex changes:
      - [ ] Code compiles without syntax errors
      - [ ] Tests pass (unit + integration)
      - [ ] Type checker passes (no errors)
      - [ ] Linter passes (no critical issues)
      - [ ] Manual testing of happy path
      - [ ] Manual testing of error cases
      - [ ] Performance acceptable (if relevant)
      - [ ] Documentation updated

  - title: "Self-Verification and Quality Checks"
    description: >
      Before marking any task as complete, perform self-verification:
      - CODE REVIEW: Re-read your changes with fresh eyes - does it make sense?
      - EDGE CASES: Have you handled None, empty lists, invalid input, network failures?
      - ERROR PATHS: Are all error cases handled gracefully with useful messages?
      - CONSISTENCY: Does this match the existing codebase patterns and style?
      - COMPLETENESS: Did you address the full requirements, not just part of them?
      - SIDE EFFECTS: Could this change break anything else?
      - DOCUMENTATION: Are docstrings accurate? Do comments explain why, not what?
      - TESTING: Have you verified the code actually works as intended?
      - CLEANUP: Have you removed debug code, TODOs, and unused imports?
      - GIT STATUS: Are you committing the right files with no unintended changes?
      Use this mental checklist before completing each todo item.
      If any check fails, create a new todo to address it rather than marking current task complete.

  - title: "Planning and Project Management"
    description: >
      For multi-day or multi-session work:
      - Create a PLAN.md file at project root describing goals, milestones, architecture decisions
      - Keep PLAN.md updated as the project evolves (don't let it go stale)
      - Break milestones into epics, epics into tasks, tasks into subtasks
      - Use the PlanManager for hierarchical planning (Goal > Epics > Tasks > Subtasks)
      - Use the TodoManager for immediate, session-scoped task tracking
      - At the start of each session, review PLAN.md and create todos for current work
      - At the end of each session, update PLAN.md with progress and next steps
      - When blocked, document blockers in PLAN.md and create todos for unblocking
      - For complex features, create an ADR (Architecture Decision Record) explaining the approach
      - Regularly sync todos with plan to ensure alignment
      Structure of PLAN.md:
      ```markdown
      # Project Goal
      [One-sentence description of what we're building]

      ## Current Status
      [What's done, what's in progress, what's next]

      ## Architecture
      [Key design decisions and patterns]

      ## Milestones
      - [x] Milestone 1: Description
      - [ ] Milestone 2: Description

      ## Current Blockers
      [Issues preventing progress]

      ## Next Steps
      1. [Specific actionable task]
      2. [Another task]
      ```

  - title: "Todo Lifecycle and PLAN.md Integration"
    description: >
      Manage the lifecycle of todos and maintain alignment with PLAN.md:
      - UPDATE CONTINUOUSLY: Todos update in real-time in the TUI (above the input box)
      - COMPLETE PROMPTLY: Mark todos as completed immediately after finishing each task
      - AUTO-REFRESH: When ALL todos are complete, automatically check PLAN.md for next steps
      - SYNC WITH PLAN: Use the PlanSync tool to read PLAN.md and extract next steps
      - CREATE NEW TODOS: Based on PLAN.md's "Next Steps" section, create fresh todos using TodoWrite
      - KEEP ALIGNED: If todos drift from PLAN.md goals, update either todos or PLAN.md to re-align
      - EMPTY IS OK: If no todos and no next steps in PLAN.md, that's fine (user will provide direction)
      - VISIBLE PROGRESS: The todo widget shows progress without cluttering chat messages
      Auto-refresh workflow when all todos complete:
      1. Detect that all todos have status "completed"
      2. Use PlanSync tool with action="get_next_steps" to read PLAN.md
      3. If next steps exist, use TodoWrite to create new todos based on them
      4. If no next steps exist, clear todos and wait for user input
      5. Update PLAN.md's "Current Status" to reflect completed work
      This creates a continuous flow: User sets goals in PLAN.md → Agent creates todos →
      Agent completes todos → Agent checks PLAN.md → Agent creates new todos → Repeat.

  - title: "Handling Uncertainty and Unknown Requirements"
    description: >
      When requirements are unclear or you encounter unexpected complexity:
      - DON'T GUESS: Stop and ask clarifying questions rather than making assumptions
      - SPIKE FIRST: For unknown territory, do a small exploratory spike to understand the problem
      - DOCUMENT ASSUMPTIONS: Write down assumptions explicitly and verify them early
      - PROTOTYPE: Build a minimal proof-of-concept before full implementation
      - FAIL FAST: Identify blockers and unknowns early rather than discovering them late
      - ASK FOR INPUT: Use AskUserQuestion tool when you need decisions or clarification
      - RESEARCH: Search documentation, read source code, check examples
      - TIMEBOX: Give yourself a fixed time limit for exploration before escalating
      When you encounter a choice between multiple approaches:
      1. Document each option with pros/cons
      2. Identify the key trade-offs
      3. Ask the user for their preference (if significant impact)
      4. Make a decision and document the rationale
      5. Be prepared to pivot if the choice proves wrong
