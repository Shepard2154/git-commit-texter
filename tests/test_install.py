import os
import subprocess
import sys
from pathlib import Path

import pytest

from git_commit_texter.cli import main
from git_commit_texter.install import NotAGitRepositoryError, install


def _git(repo: Path, *args: str) -> None:
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
    }
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )


def test_install_in_git_repo_writes_executable_prepare_commit_msg_hook(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")

    install(repo)

    hook = repo / ".git" / "hooks" / "prepare-commit-msg"
    assert hook.is_file()
    assert os.access(hook, os.X_OK)


def test_install_hook_points_at_installing_interpreter_and_package_entry(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")

    install(repo)

    hook_text = (repo / ".git" / "hooks" / "prepare-commit-msg").read_text()
    assert sys.executable in hook_text
    assert "-m git_commit_texter.hook" in hook_text


def test_install_outside_git_repo_fails_without_writing_a_hook(tmp_path: Path) -> None:
    not_a_repo = tmp_path / "not-a-repo"
    not_a_repo.mkdir()

    with pytest.raises(NotAGitRepositoryError, match="git repository"):
        install(not_a_repo)

    assert not (not_a_repo / ".git").exists()
    assert not (not_a_repo / "prepare-commit-msg").exists()


def test_cli_install_writes_hook_in_current_git_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    monkeypatch.chdir(repo)

    assert main(["install"]) == 0

    hook = repo / ".git" / "hooks" / "prepare-commit-msg"
    assert hook.is_file()
    assert os.access(hook, os.X_OK)
    assert sys.executable in hook.read_text()


def test_cli_install_outside_git_repo_fails_clearly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    not_a_repo = tmp_path / "not-a-repo"
    not_a_repo.mkdir()
    monkeypatch.chdir(not_a_repo)

    assert main(["install"]) != 0

    captured = capsys.readouterr()
    assert "git repository" in captured.err
    assert captured.out == ""
    assert not (not_a_repo / ".git").exists()
