from pathlib import Path

import pytest

from git_commit_texter import SuccessfulDraft, prepare_commit_message

GIT_HELP = """\
# Please enter the commit message for your changes. Lines starting
# with '#' will be ignored, and an empty message aborts the commit.
#
# On branch main
# Changes to be committed:
#	modified:   src/fetch.py
#
"""

STAGED_DIFF = """\
diff --git a/src/fetch.py b/src/fetch.py
index 1111111..2222222 100644
--- a/src/fetch.py
+++ b/src/fetch.py
@@ -1,4 +1,12 @@
 def fetch(url):
+    delay = 0.1
+    for attempt in range(3):
+        try:
             return get(url)
+        except Timeout:
+            time.sleep(delay)
+            delay *= 2
+    raise FetchError(url)
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

WHITESPACE_ONLY_DIFF = """\
diff --git a/src/fetch.py b/src/fetch.py
index 1111111..2222222 100644
--- a/src/fetch.py
+++ b/src/fetch.py
@@ -1,3 +1,4 @@
 def fetch(url):
+    
     return get(url)
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

LOCKFILE_ONLY_DIFF = """\
diff --git a/poetry.lock b/poetry.lock
index 1111111..2222222 100644
--- a/poetry.lock
+++ b/poetry.lock
@@ -1,3 +1,6 @@
 [[package]]
+name = "requests"
+version = "2.32.0"
+
"""

LOCKFILE_ONLY_EDITOR = """\
chore(deps): bump requests to 2.32.0

# Steps:
# 1. Record the requests 2.32.0 lockfile bump

# Please enter the commit message for your changes. Lines starting
# with '#' will be ignored, and an empty message aborts the commit.
#
# On branch main
# Changes to be committed:
#	modified:   src/fetch.py
#
"""


class FakeGit:
    def __init__(self, staged_diff: str) -> None:
        self._staged_diff = staged_diff
        self.staged_diff_calls = 0

    def staged_diff(self) -> str:
        self.staged_diff_calls += 1
        return self._staged_diff


class FakeLlm:
    def __init__(self, reply: SuccessfulDraft) -> None:
        self._reply = reply
        self.received_diffs: list[str] = []

    def draft(self, staged_diff: str) -> SuccessfulDraft:
        self.received_diffs.append(staged_diff)
        return self._reply


@pytest.mark.parametrize("source", [None, "", "template"])
def test_finished_iteration_writes_placeholder_steps_and_preserves_git_help(
    tmp_path: Path, source: str | None
) -> None:
    editor = tmp_path / "COMMIT_EDITMSG"
    editor.write_text("\n" + GIT_HELP)

    git = FakeGit(STAGED_DIFF)
    llm = FakeLlm(
        SuccessfulDraft(
            placeholder="feat(fetch): add retry with backoff",
            steps=(
                "Add exponential backoff to the fetch client",
                "Stop retrying after the last failed attempt",
            ),
        )
    )

    result = prepare_commit_message(editor, git, llm, source)

    assert result == 0
    assert editor.read_text() == EXPECTED_EDITOR
    assert git.staged_diff_calls == 1
    assert llm.received_diffs == [STAGED_DIFF]


@pytest.mark.parametrize("source", ["message", "merge", "squash", "commit"])
def test_git_owned_source_leaves_editor_unchanged_and_does_not_call_llm(
    tmp_path: Path, source: str
) -> None:
    original = "fix: caller already wrote this\n\n" + GIT_HELP
    editor = tmp_path / "COMMIT_EDITMSG"
    editor.write_text(original)

    git = FakeGit(STAGED_DIFF)
    llm = FakeLlm(
        SuccessfulDraft(
            placeholder="feat(fetch): add retry with backoff",
            steps=("Add exponential backoff to the fetch client",),
        )
    )

    result = prepare_commit_message(editor, git, llm, source)

    assert result == 0
    assert editor.read_text() == original
    assert git.staged_diff_calls == 0
    assert llm.received_diffs == []


def test_whitespace_only_diff_writes_too_early_and_does_not_call_llm(
    tmp_path: Path,
) -> None:
    editor = tmp_path / "COMMIT_EDITMSG"
    editor.write_text("\n" + GIT_HELP)

    git = FakeGit(WHITESPACE_ONLY_DIFF)
    llm = FakeLlm(
        SuccessfulDraft(
            placeholder="feat(fetch): add retry with backoff",
            steps=("should not appear",),
        )
    )

    result = prepare_commit_message(editor, git, llm)

    assert result == 0
    assert editor.read_text() == WHITESPACE_ONLY_EDITOR
    assert git.staged_diff_calls == 1
    assert llm.received_diffs == []


def test_empty_index_writes_error_and_does_not_call_llm(tmp_path: Path) -> None:
    editor = tmp_path / "COMMIT_EDITMSG"
    editor.write_text("\n" + GIT_HELP)

    git = FakeGit("")
    llm = FakeLlm(
        SuccessfulDraft(
            placeholder="feat(fetch): add retry with backoff",
            steps=("should not appear",),
        )
    )

    result = prepare_commit_message(editor, git, llm)

    assert result == 0
    assert editor.read_text() == EMPTY_INDEX_EDITOR
    assert git.staged_diff_calls == 1
    assert llm.received_diffs == []


def test_lockfile_only_diff_still_calls_llm(tmp_path: Path) -> None:
    editor = tmp_path / "COMMIT_EDITMSG"
    editor.write_text("\n" + GIT_HELP)

    git = FakeGit(LOCKFILE_ONLY_DIFF)
    llm = FakeLlm(
        SuccessfulDraft(
            placeholder="chore(deps): bump requests to 2.32.0",
            steps=("Record the requests 2.32.0 lockfile bump",),
        )
    )

    result = prepare_commit_message(editor, git, llm)

    assert result == 0
    assert editor.read_text() == LOCKFILE_ONLY_EDITOR
    assert git.staged_diff_calls == 1
    assert llm.received_diffs == [LOCKFILE_ONLY_DIFF]
