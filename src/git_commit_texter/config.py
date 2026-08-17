from __future__ import annotations

import os
import tomllib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

_DEFAULT_MODEL = "qwen3.5:4b"
_DEFAULT_HOST = "localhost:11434"
_Adapter = TypeVar("_Adapter")


@dataclass(frozen=True)
class RuntimeConfig:
    model: str
    host: str


def resolve_runtime_config(
    project_root: Path,
    environ: Mapping[str, str] | None = None,
) -> RuntimeConfig:
    env = os.environ if environ is None else environ
    file_config = _pyproject_overrides(project_root)
    return RuntimeConfig(
        model=(
            _nonempty_str(env.get("GIT_COMMIT_TEXTER_MODEL"))
            or file_config.model
            or _DEFAULT_MODEL
        ),
        host=(
            _nonempty_str(env.get("OLLAMA_HOST")) or file_config.host or _DEFAULT_HOST
        ),
    )


def build_llm_adapter(
    factory: Callable[[str, str], _Adapter],
    project_root: Path,
    environ: Mapping[str, str] | None = None,
) -> _Adapter:
    config = resolve_runtime_config(project_root, environ)
    return factory(config.model, config.host)


@dataclass(frozen=True)
class _FileOverrides:
    model: str | None
    host: str | None


def _pyproject_overrides(project_root: Path) -> _FileOverrides:
    pyproject = project_root / "pyproject.toml"
    if not pyproject.is_file():
        return _FileOverrides(model=None, host=None)
    with pyproject.open("rb") as file:
        data = tomllib.load(file)
    tool = data.get("tool", {})
    if not isinstance(tool, dict):
        return _FileOverrides(model=None, host=None)
    section = tool.get("git-commit-texter", {})
    if not isinstance(section, dict):
        return _FileOverrides(model=None, host=None)
    return _FileOverrides(
        model=_nonempty_str(section.get("model")),
        host=_nonempty_str(section.get("host")),
    )


def _nonempty_str(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None
