import socket
import threading
import time
from pathlib import Path

from git_commit_texter import OllamaLlm, build_llm_adapter, prepare_commit_message

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

UNREACHABLE_EDITOR = """\
# Error: LLM unreachable

# Please enter the commit message for your changes. Lines starting
# with '#' will be ignored, and an empty message aborts the commit.
#
# On branch main
# Changes to be committed:
#	modified:   src/fetch.py
#
"""

TIMEOUT_EDITOR = """\
# Error: LLM timed out

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

    def staged_diff(self) -> str:
        return self._staged_diff


class _HangingServer:
    def __init__(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(1)
        self.port = self._sock.getsockname()[1]
        self._thread = threading.Thread(target=self._serve, daemon=True)

    def _serve(self) -> None:
        try:
            conn, _ = self._sock.accept()
            time.sleep(5)
            conn.close()
        except OSError:
            pass

    def __enter__(self) -> int:
        self._thread.start()
        return self.port

    def __exit__(self, *_args: object) -> None:
        self._sock.close()


def _closed_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_defaults_construct_production_adapter_without_calling_ollama(
    tmp_path: Path,
) -> None:
    llm = build_llm_adapter(OllamaLlm, tmp_path, environ={})

    assert llm.model == "qwen3.5:4b"
    assert llm.host == "localhost:11434"


def test_unreachable_daemon_writes_error_and_does_not_invent_placeholder(
    tmp_path: Path,
) -> None:
    editor = tmp_path / "COMMIT_EDITMSG"
    editor.write_text("\n" + GIT_HELP)
    llm = OllamaLlm("qwen3.5:4b", f"127.0.0.1:{_closed_port()}")

    result = prepare_commit_message(editor, FakeGit(STAGED_DIFF), llm)

    assert result == 0
    assert editor.read_text() == UNREACHABLE_EDITOR


def test_request_timeout_writes_error_and_does_not_invent_placeholder(
    tmp_path: Path,
) -> None:
    editor = tmp_path / "COMMIT_EDITMSG"
    editor.write_text("\n" + GIT_HELP)
    with _HangingServer() as port:
        llm = OllamaLlm("qwen3.5:4b", f"127.0.0.1:{port}", timeout=0.3)
        result = prepare_commit_message(editor, FakeGit(STAGED_DIFF), llm)

    assert result == 0
    assert editor.read_text() == TIMEOUT_EDITOR
