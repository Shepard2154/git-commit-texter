from __future__ import annotations

import subprocess
from pathlib import Path


class StagedDiffGit:
    def __init__(self, repo: Path) -> None:
        self._repo = repo

    def staged_diff(self) -> str:
        result = subprocess.run(
            [
                "git",
                "--no-pager",
                "-C",
                str(self._repo),
                "diff",
                "--cached",
                "--no-color",
                "--no-ext-diff",
            ],
            check=True,
            capture_output=True,
            encoding="utf-8",
        )
        return result.stdout
