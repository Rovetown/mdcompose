<!--
What does this change, and why. Link the issue if there is one.
-->

## Checklist

- [ ] `uv run pytest` passes, and so does `uv sync --locked --python 3.11 && uv run --no-sync pytest`
- [ ] `uv run ruff check .` is clean
- [ ] `uv run pre-commit run --all-files` is clean
- [ ] Every commit is a Conventional Commit (`uv run cz check --rev-range origin/main..HEAD`)
- [ ] Plain ASCII in everything the change adds
- [ ] Behavior change: `docs/core-contract.md` updated in the same commit
