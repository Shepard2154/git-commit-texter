from pathlib import Path

from git_commit_texter import SuccessfulDraft, build_llm_adapter


class FakeConfiguredLlm:
    def __init__(self, model: str, host: str) -> None:
        self.model = model
        self.host = host

    def draft(self, staged_diff: str) -> SuccessfulDraft:
        return SuccessfulDraft(placeholder="unused", steps=("unused",))


def test_defaults_construct_adapter_with_package_model_and_host(tmp_path: Path) -> None:
    llm = build_llm_adapter(FakeConfiguredLlm, tmp_path, environ={})

    assert llm.model == "qwen3.5:4b"
    assert llm.host == "localhost:11434"


def test_pyproject_without_tool_section_keeps_package_defaults(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """\
[project]
name = "host-app"
"""
    )

    llm = build_llm_adapter(FakeConfiguredLlm, tmp_path, environ={})

    assert llm.model == "qwen3.5:4b"
    assert llm.host == "localhost:11434"


def test_pyproject_overrides_package_defaults(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """\
[tool.git-commit-texter]
model = "phi4-mini"
host = "ollama.internal:11434"
"""
    )

    llm = build_llm_adapter(FakeConfiguredLlm, tmp_path, environ={})

    assert llm.model == "phi4-mini"
    assert llm.host == "ollama.internal:11434"


def test_environment_overrides_pyproject(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """\
[tool.git-commit-texter]
model = "phi4-mini"
host = "ollama.internal:11434"
"""
    )

    llm = build_llm_adapter(
        FakeConfiguredLlm,
        tmp_path,
        environ={
            "GIT_COMMIT_TEXTER_MODEL": "llama3.2:3b",
            "OLLAMA_HOST": "127.0.0.1:12345",
        },
    )

    assert llm.model == "llama3.2:3b"
    assert llm.host == "127.0.0.1:12345"
