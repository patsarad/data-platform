# Installing this documentation bundle

This ZIP mirrors the files intended to be copied into the repository root.

## Public files to commit

Copy and commit:

- `docs/` **except** `docs/portfolio/`
- `AGENTS.md` (replacement for the existing file)
- `README.md` (replacement for the current minimal README)

The public docs are intentionally written so a reviewer can see the target architecture while clearly distinguishing unfinished work in `docs/CURRENT_STATE.md`.

## Private files to keep local

Keep `docs/portfolio/` locally for interview/resume preparation. Add this line to the root `.gitignore` before copying the folder into the repo:

```gitignore
docs/portfolio/
```

This is preferable to hiding the entire `docs/` directory. Architecture, setup, current-state, roadmap, testing, and pipeline documentation are useful evidence for a reviewer. Interview talking points and resume drafting notes are not.

## `.gitignore`

`GITIGNORE_ADDITIONS.txt` contains the recommended ignore rules. Merge them into the existing root `.gitignore`; do not replace unrelated ignore rules blindly.

## Existing planning files

Once these docs are installed, the old `PROJECT_PLAN.md` and `PROJECT_CONTEXT.md` are redundant. Keep them temporarily if desired, but Codex should use the new `docs/` files as the source of truth. After you are comfortable with the replacement, they can be removed in a normal reviewed commit.
