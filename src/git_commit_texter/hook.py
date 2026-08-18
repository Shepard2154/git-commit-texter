from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

from git_commit_texter.config import build_llm_adapter
from git_commit_texter.git import StagedDiffGit
from git_commit_texter.llm import OllamaLlm
from git_commit_texter.prepare_commit_message import prepare_commit_message


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    editor_file = Path(args[0])
    source = args[1] if len(args) > 1 else None
    repo = Path.cwd()
    git = StagedDiffGit(repo)
    llm = build_llm_adapter(OllamaLlm, repo)
    return prepare_commit_message(editor_file, git, llm, source)


if __name__ == "__main__":
    raise SystemExit(main())
