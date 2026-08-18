from __future__ import annotations

import httpx
from langchain_ollama import ChatOllama

from git_commit_texter.prepare_commit_message import (
    LlmFailure,
    SuccessfulDraft,
    TooEarlyJudgement,
)

_REQUEST_TIMEOUT_SECONDS = 30.0


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
            client_kwargs={"timeout": timeout},
        )

    def draft(
        self, staged_diff: str
    ) -> SuccessfulDraft | TooEarlyJudgement | LlmFailure:
        try:
            self._chat.invoke(staged_diff)
        except httpx.TimeoutException:
            return LlmFailure(kind="timeout")
        except (ConnectionError, httpx.ConnectError):
            return LlmFailure(kind="unreachable")
        return LlmFailure(kind="unusable")


def _base_url(host: str) -> str:
    if "://" in host:
        return host
    return f"http://{host}"
