from __future__ import annotations

import json
import re
from typing import Any

import httpx
from langchain_ollama import ChatOllama

from git_commit_texter.prepare_commit_message import (
    LlmFailure,
    SuccessfulDraft,
    TooEarlyJudgement,
)

_REQUEST_TIMEOUT_SECONDS = 30.0
_SUBJECT = re.compile(
    r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)"
    r"(\([^)]+\))?: .+"
)
_PROMPT = """\
Draft a git commit from this staged diff.

Return JSON only, one of:
{{"placeholder":"<conventional commit>","steps":["<step>"]}}
{{"too_early":"<why the work is unfinished>"}}

Rules:
- if the staged work looks like a finished iteration, return placeholder and steps
- if it looks unfinished or mixed leftover, return too_early with only the reason; do not suggest a subject
- placeholder is one English Conventional Commits subject: type(scope): description
- scope is optional; do not invent a scope
- type must be feat, fix, docs, style, refactor, perf, test, build, ci, chore, or revert
- add a body after a blank line only for a BREAKING CHANGE or text that must survive in git history
- steps describe the meaning of the iteration, not a copy of git status

Staged diff:
{diff}
"""


class OllamaLlm:
    def __init__(
        self,
        model: str,
        host: str,
        timeout: float = _REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        self.model = model
        self.host = host
        self._chat = ChatOllama(
            model=model,
            base_url=_base_url(host),
            validate_model_on_init=False,
            format="json",
            reasoning=False,
            client_kwargs={"timeout": timeout},
        )

    def draft(
        self, staged_diff: str
    ) -> SuccessfulDraft | TooEarlyJudgement | LlmFailure:
        try:
            message = self._chat.invoke(_PROMPT.format(diff=staged_diff))
        except httpx.TimeoutException:
            return LlmFailure(kind="timeout")
        except (ConnectionError, httpx.ConnectError):
            return LlmFailure(kind="unreachable")
        except Exception as exc:
            if _is_context_too_large(exc):
                return LlmFailure(kind="context_too_large")
            return LlmFailure(kind="unusable")
        return _parse(message.content)


def _parse(content: Any) -> SuccessfulDraft | TooEarlyJudgement | LlmFailure:
    try:
        data = json.loads(_message_text(content))
    except json.JSONDecodeError:
        return LlmFailure(kind="unusable")
    if not isinstance(data, dict):
        return LlmFailure(kind="unusable")
    too_early = data.get("too_early")
    if isinstance(too_early, str) and too_early.strip():
        return TooEarlyJudgement(reason=too_early.strip())
    placeholder = data.get("placeholder")
    steps = data.get("steps")
    if not isinstance(placeholder, str) or not isinstance(steps, list):
        return LlmFailure(kind="unusable")
    cleaned_steps = tuple(
        step.strip() for step in steps if isinstance(step, str) and step.strip()
    )
    placeholder = placeholder.strip()
    if cleaned_steps and _SUBJECT.fullmatch(placeholder.splitlines()[0]):
        return SuccessfulDraft(placeholder=placeholder, steps=cleaned_steps)
    return LlmFailure(kind="unusable")


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    return ""


def _is_context_too_large(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "context length" in text or "context window" in text


def _base_url(host: str) -> str:
    if "://" in host:
        return host
    return f"http://{host}"
