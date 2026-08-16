from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class SuccessfulDraft:
    placeholder: str
    steps: tuple[str, ...]


class GitAdapter(Protocol):
    def staged_diff(self) -> str: ...


class LlmAdapter(Protocol):
    def draft(self, staged_diff: str) -> SuccessfulDraft: ...


def prepare_commit_message(
    editor_file: Path,
    git: GitAdapter,
    llm: LlmAdapter,
) -> int:
    original = editor_file.read_text()
    draft = llm.draft(git.staged_diff())
    editor_file.write_text(_render_success(draft, _git_help_block(original)))
    return 0


def _git_help_block(original: str) -> str:
    lines = original.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if line.startswith("#"):
            return "".join(lines[index:])
    return ""


def _render_success(draft: SuccessfulDraft, git_help: str) -> str:
    numbered = "\n".join(
        f"# {index}. {step}" for index, step in enumerate(draft.steps, start=1)
    )
    agent_block = f"{draft.placeholder}\n\n# Steps:\n{numbered}\n"
    if not git_help:
        return agent_block
    return f"{agent_block}\n{git_help}"
