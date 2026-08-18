from __future__ import annotations

import subprocess
import sys
from pathlib import Path


class NotAGitRepositoryError(Exception):
    pass


def install(repo: Path) -> None:
    hook = _hooks_dir(repo) / "prepare-commit-msg"
    hook.write_text(_hook_script(sys.executable))
    hook.chmod(0o755)


def _hooks_dir(repo: Path) -> Path:
    result = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--git-path", "hooks"],
        capture_output=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise NotAGitRepositoryError(
            "Not a git repository. Run git-commit-texter install from a git checkout."
        )
    hooks = Path(result.stdout.strip())
    if not hooks.is_absolute():
        hooks = repo / hooks
    return hooks


def _hook_script(python: str) -> str:
    quoted = python.replace("'", "'\\''")
    return f"""\
#!/bin/sh
exec '{quoted}' -m git_commit_texter.hook "$@"
"""
