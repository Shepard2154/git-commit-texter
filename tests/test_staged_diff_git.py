import os
import subprocess
from pathlib import Path

import pytest

from git_commit_texter import StagedDiffGit, SuccessfulDraft, prepare_commit_message

GIT_HELP = """\
# Please enter the commit message for your changes. Lines starting
# with '#' will be ignored, and an empty message aborts the commit.
#
# On branch main
# Changes to be committed:
#	modified:   src/fetch.py
#
"""

EXPECTED_EDITOR = """\
feat(fetch): add retry with backoff

# Steps:
# 1. Add exponential backoff to the fetch client
# 2. Stop retrying after the last failed attempt

# Please enter the commit message for your changes. Lines starting
# with '#' will be ignored, and an empty message aborts the commit.
#
# On branch main
# Changes to be committed:
#	modified:   src/fetch.py
#
"""

EMPTY_INDEX_EDITOR = """\
# Error: nothing staged

# Please enter the commit message for your changes. Lines starting
# with '#' will be ignored, and an empty message aborts the commit.
#
# On branch main
# Changes to be committed:
#	modified:   src/fetch.py
#
"""

WHITESPACE_ONLY_EDITOR = """\
# Too early: staged diff is whitespace-only

# Please enter the commit message for your changes. Lines starting
# with '#' will be ignored, and an empty message aborts the commit.
#
# On branch main
# Changes to be committed:
#	modified:   src/fetch.py
#
"""

_STAGED_LINE = "    delay = 0.1"
_UNSTAGED_LINE = "    print('beta-debug-print-unstaged')"
_UNTRACKED_MARKER = "gamma-scratch-untracked"
_BRANCH = "topic-branch-name-must-not-leak"
_HISTORY_SUBJECT = "history-subject-must-not-leak"


class FakeLlm:
    def __init__(self, reply: SuccessfulDraft) -> None:
        self._reply = reply
        self.received_diffs: list[str] = []

    def draft(self, staged_diff: str) -> SuccessfulDraft:
        self.received_diffs.append(staged_diff)
        return self._reply


def _git(repo: Path, *args: str) -> None:
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_AUTHOR_NAME": "Texter",
        "GIT_AUTHOR_EMAIL": "texter@example.test",
        "GIT_COMMITTER_NAME": "Texter",
        "GIT_COMMITTER_EMAIL": "texter@example.test",
    }
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )


def _init_repo(repo: Path) -> None:
    repo.mkdir()
    _git(repo, "init", "-b", _BRANCH)
    _git(repo, "config", "user.name", "Texter")
    _git(repo, "config", "user.email", "texter@example.test")
    _git(repo, "config", "commit.gpgsign", "false")


def _seed_repo(tmp_path: Path, commit_message: str = "seed") -> Path:
    repo = tmp_path / "repo"
    _init_repo(repo)
    tracked = repo / "src" / "fetch.py"
    tracked.parent.mkdir()
    tracked.write_text("def fetch(url):\n    return get(url)\n")
    _git(repo, "add", "src/fetch.py")
    _git(repo, "commit", "-m", commit_message)
    return repo


def _successful_llm() -> FakeLlm:
    return FakeLlm(
        SuccessfulDraft(
            placeholder="feat(fetch): add retry with backoff",
            steps=(
                "Add exponential backoff to the fetch client",
                "Stop retrying after the last failed attempt",
            ),
        )
    )


def test_prepare_commit_message_reads_only_staged_hunks_from_real_repo(
    tmp_path: Path,
) -> None:
    repo = _seed_repo(tmp_path, _HISTORY_SUBJECT)
    tracked = repo / "src" / "fetch.py"
    tracked.write_text(f"def fetch(url):\n{_STAGED_LINE}\n    return get(url)\n")
    _git(repo, "add", "src/fetch.py")
    tracked.write_text(
        f"def fetch(url):\n{_STAGED_LINE}\n{_UNSTAGED_LINE}\n    return get(url)\n"
    )
    (repo / "scratch.py").write_text(f"{_UNTRACKED_MARKER}\n")

    editor = tmp_path / "COMMIT_EDITMSG"
    editor.write_text("\n" + GIT_HELP)
    llm = _successful_llm()

    result = prepare_commit_message(editor, StagedDiffGit(repo), llm)

    assert result == 0
    assert editor.read_text() == EXPECTED_EDITOR
    assert len(llm.received_diffs) == 1
    received = llm.received_diffs[0]
    assert _STAGED_LINE in received
    assert _UNSTAGED_LINE not in received
    assert _UNTRACKED_MARKER not in received
    assert _BRANCH not in received
    assert _HISTORY_SUBJECT not in received


@pytest.mark.parametrize("source", ["message", "merge", "squash", "commit"])
def test_git_owned_source_leaves_editor_unchanged_with_real_git(
    tmp_path: Path, source: str
) -> None:
    repo = _seed_repo(tmp_path)
    tracked = repo / "src" / "fetch.py"
    tracked.write_text(f"def fetch(url):\n{_STAGED_LINE}\n    return get(url)\n")
    _git(repo, "add", "src/fetch.py")

    original = "fix: caller already wrote this\n\n" + GIT_HELP
    editor = tmp_path / "COMMIT_EDITMSG"
    editor.write_text(original)
    llm = _successful_llm()

    result = prepare_commit_message(editor, StagedDiffGit(repo), llm, source)

    assert result == 0
    assert editor.read_text() == original
    assert llm.received_diffs == []


def test_empty_index_with_unstaged_work_writes_error_and_skips_llm(
    tmp_path: Path,
) -> None:
    repo = _seed_repo(tmp_path)
    tracked = repo / "src" / "fetch.py"
    tracked.write_text(f"def fetch(url):\n{_UNSTAGED_LINE}\n    return get(url)\n")
    (repo / "scratch.py").write_text(f"{_UNTRACKED_MARKER}\n")

    editor = tmp_path / "COMMIT_EDITMSG"
    editor.write_text("\n" + GIT_HELP)
    llm = _successful_llm()

    result = prepare_commit_message(editor, StagedDiffGit(repo), llm)

    assert result == 0
    assert editor.read_text() == EMPTY_INDEX_EDITOR
    assert llm.received_diffs == []


def test_whitespace_only_staged_diff_with_unstaged_work_skips_llm(
    tmp_path: Path,
) -> None:
    repo = _seed_repo(tmp_path)
    tracked = repo / "src" / "fetch.py"
    tracked.write_text("def fetch(url):\n    \n    return get(url)\n")
    _git(repo, "add", "src/fetch.py")
    tracked.write_text(
        f"def fetch(url):\n    \n{_UNSTAGED_LINE}\n    return get(url)\n"
    )

    editor = tmp_path / "COMMIT_EDITMSG"
    editor.write_text("\n" + GIT_HELP)
    llm = _successful_llm()

    result = prepare_commit_message(editor, StagedDiffGit(repo), llm)

    assert result == 0
    assert editor.read_text() == WHITESPACE_ONLY_EDITOR
    assert llm.received_diffs == []
