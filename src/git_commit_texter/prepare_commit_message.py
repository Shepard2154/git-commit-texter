from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

_SKIP_SOURCES = frozenset({"message", "merge", "squash", "commit"})


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
    source: str | None = None,
) -> int:
    if source in _SKIP_SOURCES:
        return 0
    original = editor_file.read_text()
    git_help = _git_help_block(original)
    staged_diff = git.staged_diff()
    if not staged_diff.strip():
        editor_file.write_text(_render_comment("# Error: nothing staged", git_help))
        return 0
    if _whitespace_only_changes(staged_diff):
        editor_file.write_text(
            _render_comment("# Too early: staged diff is whitespace-only", git_help)
        )
        return 0
    draft = llm.draft(staged_diff)
    editor_file.write_text(_render_success(draft, git_help))
    return 0


def _whitespace_only_changes(staged_diff: str) -> bool:
    changed_lines = [
        line[1:]
        for line in staged_diff.splitlines()
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
    ]
    return bool(changed_lines) and all(not line.strip() for line in changed_lines)


def _git_help_block(original: str) -> str:
    lines = original.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if line.startswith("#"):
            return "".join(lines[index:])
    return ""


def _render_comment(comment: str, git_help: str) -> str:
    return _with_git_help(f"{comment}\n", git_help)


def _render_success(draft: SuccessfulDraft, git_help: str) -> str:
    numbered = "\n".join(
        f"# {index}. {step}" for index, step in enumerate(draft.steps, start=1)
    )
    return _with_git_help(f"{draft.placeholder}\n\n# Steps:\n{numbered}\n", git_help)


def _with_git_help(agent_block: str, git_help: str) -> str:
    if not git_help:
        return agent_block
    return f"{agent_block}\n{git_help}"
