from pathlib import Path

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


def test_finished_iteration_writes_placeholder_steps_and_preserves_git_help(
    tmp_path: Path,
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

    result = prepare_commit_message(editor, git, llm)

    assert result == 0
    assert editor.read_text() == EXPECTED_EDITOR
    assert git.staged_diff_calls == 1
    assert llm.received_diffs == [STAGED_DIFF]
