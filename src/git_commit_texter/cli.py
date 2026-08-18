from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

from git_commit_texter.install import NotAGitRepositoryError, install


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["install"]:
        try:
            install(Path.cwd())
        except NotAGitRepositoryError as exc:
            print(exc, file=sys.stderr)
            return 1
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
