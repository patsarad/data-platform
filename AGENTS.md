# AGENTS.md

## Purpose
This file defines how the AI agent (Codex) should behave when working on this repository.

---

## General Rules

- Do NOT rewrite large parts of the codebase unnecessarily
- Make small, incremental, reviewable changes
- Always prioritize clarity and simplicity over complexity
- Prefer working code over perfect code

---

## Workflow Expectations

When implementing features:

1. Read PROJECT_PLAN.md before making changes
2. Identify the current milestone
3. Only implement one logical unit at a time
4. Ensure code runs before moving on

---

## Code Generation Guidelines

- Write modular, production-style Python code
- Use functions instead of long scripts
- Add docstrings to all functions
- Use type hints where appropriate
- Use logging instead of print statements

---

## File Safety Rules

- Do NOT modify unrelated files
- Do NOT delete existing code unless explicitly instructed
- Do NOT refactor entire modules without approval

---

## Testing Requirements

- Add tests when implementing new logic
- Ensure tests pass before completing a task

---

## Output Expectations

For each task:

- Clearly state what was implemented
- List files that were created or modified
- Explain any important design decisions briefly

---

## Error Handling

- Handle API failures with retries
- Add basic exception handling
- Log meaningful error messages

---

## Task Size Constraint

- Each task should be small enough to review in 15–30 minutes
- If a task is too large, break it into smaller steps

---

## When Uncertain

- Choose the simplest working implementation
- Avoid over-engineering
- Add comments explaining assumptions

---

## Priority Order

1. Functionality
2. Readability
3. Modularity
4. Optimization

---

## End Goal

Produce a clean, understandable, end-to-end data engineering pipeline that:
- Can be explained in an interview
- Demonstrates real-world engineering practices
- Is easy to run locally with Docker
