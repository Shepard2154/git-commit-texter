import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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

SUCCESS_EDITOR = """\
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

SUCCESS_REPLY = json.dumps(
    {
        "placeholder": "feat(fetch): add retry with backoff",
        "steps": [
            "Add exponential backoff to the fetch client",
            "Stop retrying after the last failed attempt",
        ],
    }
)

TOO_EARLY_EDITOR = """\
# Too early: unfinished slice of a feature

# Please enter the commit message for your changes. Lines starting
# with '#' will be ignored, and an empty message aborts the commit.
#
# On branch main
# Changes to be committed:
#	modified:   src/fetch.py
#
"""

TOO_EARLY_REPLY = json.dumps({"too_early": "unfinished slice of a feature"})

UNUSABLE_EDITOR = """\
# Error: unusable model output

# Please enter the commit message for your changes. Lines starting
# with '#' will be ignored, and an empty message aborts the commit.
#
# On branch main
# Changes to be committed:
#	modified:   src/fetch.py
#
"""

CONTEXT_EDITOR = """\
# Error: staged diff exceeds model context

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


class _CannedOllama:
    def __init__(self, content: str) -> None:
        content_bytes = (
            json.dumps(
                {
                    "model": "qwen3.5:4b",
                    "message": {"role": "assistant", "content": content},
                    "done": True,
                }
            )
            + "\n"
        ).encode()

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args: object) -> None:
                return

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                self.rfile.read(length)
                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson")
                self.send_header("Content-Length", str(len(content_bytes)))
                self.end_headers()
                self.wfile.write(content_bytes)

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self._httpd.server_address[1]
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    def __enter__(self) -> int:
        self._thread.start()
        return self.port

    def __exit__(self, *_args: object) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()


class _OllamaHttpError:
    def __init__(self, status: int, body: bytes) -> None:
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args: object) -> None:
                return

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                self.rfile.read(length)
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self._httpd.server_address[1]
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    def __enter__(self) -> int:
        self._thread.start()
        return self.port

    def __exit__(self, *_args: object) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()


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


def test_usable_model_reply_writes_placeholder_and_steps(tmp_path: Path) -> None:
    editor = tmp_path / "COMMIT_EDITMSG"
    editor.write_text("\n" + GIT_HELP)
    with _CannedOllama(SUCCESS_REPLY) as port:
        llm = OllamaLlm("qwen3.5:4b", f"127.0.0.1:{port}")
        result = prepare_commit_message(editor, FakeGit(STAGED_DIFF), llm)

    assert result == 0
    assert editor.read_text() == SUCCESS_EDITOR


def test_too_early_model_reply_writes_reason_without_placeholder(
    tmp_path: Path,
) -> None:
    editor = tmp_path / "COMMIT_EDITMSG"
    editor.write_text("\n" + GIT_HELP)
    with _CannedOllama(TOO_EARLY_REPLY) as port:
        llm = OllamaLlm("qwen3.5:4b", f"127.0.0.1:{port}")
        result = prepare_commit_message(editor, FakeGit(STAGED_DIFF), llm)

    assert result == 0
    assert editor.read_text() == TOO_EARLY_EDITOR


def test_garbage_model_reply_writes_unusable_error(tmp_path: Path) -> None:
    editor = tmp_path / "COMMIT_EDITMSG"
    editor.write_text("\n" + GIT_HELP)
    with _CannedOllama("lorem ipsum not a commit") as port:
        llm = OllamaLlm("qwen3.5:4b", f"127.0.0.1:{port}")
        result = prepare_commit_message(editor, FakeGit(STAGED_DIFF), llm)

    assert result == 0
    assert editor.read_text() == UNUSABLE_EDITOR


def test_unexpected_llm_error_writes_unusable_and_does_not_crash(
    tmp_path: Path,
) -> None:
    editor = tmp_path / "COMMIT_EDITMSG"
    editor.write_text("\n" + GIT_HELP)
    with _OllamaHttpError(500, b"internal") as port:
        llm = OllamaLlm("qwen3.5:4b", f"127.0.0.1:{port}")
        result = prepare_commit_message(editor, FakeGit(STAGED_DIFF), llm)

    assert result == 0
    assert editor.read_text() == UNUSABLE_EDITOR


def test_context_overflow_writes_error_without_truncating_or_crashing(
    tmp_path: Path,
) -> None:
    editor = tmp_path / "COMMIT_EDITMSG"
    editor.write_text("\n" + GIT_HELP)
    body = (
        json.dumps({"error": "the input length exceeds the context length"}) + "\n"
    ).encode()
    with _OllamaHttpError(200, body) as port:
        llm = OllamaLlm("qwen3.5:4b", f"127.0.0.1:{port}")
        result = prepare_commit_message(editor, FakeGit(STAGED_DIFF), llm)

    assert result == 0
    assert editor.read_text() == CONTEXT_EDITOR
