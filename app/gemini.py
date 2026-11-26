"""Gemini REST client with model fail-over.

If one model is overloaded (HTTP 503), rate limited (429), slow, or retired (404), the next model in
the list is tried. If every model fails, Gemini is paused briefly so the app answers instantly with
its rule-based text instead of making every user wait. The API key goes in a header, never a URL.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any, Callable, Mapping, Sequence

import requests

log = logging.getLogger(__name__)

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
_MODEL_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
# Newer Gemini models spend part of this budget "thinking" before they answer, so keep it generous.
DEFAULT_MAX_TOKENS = 4096
# Temporary problems on one model: worth trying the next model. 400/401/403 (bad key or request) are not.
RETRYABLE_STATUSES = frozenset({404, 429, 500, 502, 503, 504})


class GeminiError(Exception):
    """Any failure talking to Gemini. Callers fall back to rule-based output."""

    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


def _post(url: str, headers: Mapping[str, str], body: Mapping[str, Any], timeout: float) -> Mapping[str, Any]:
    try:
        response = requests.post(url, headers=headers, json=body, timeout=timeout)
    except requests.RequestException as err:
        raise GeminiError(f"network error: {type(err).__name__}", retryable=True) from None
    if not response.ok:
        detail = ""
        try:
            detail = str(response.json().get("error", {}).get("message", ""))[:200]
        except (ValueError, AttributeError):
            pass
        raise GeminiError(f"HTTP {response.status_code}: {detail}", retryable=response.status_code in RETRYABLE_STATUSES)
    try:
        data = response.json()
    except ValueError:
        raise GeminiError("response was not JSON", retryable=True) from None
    if not isinstance(data, dict):
        raise GeminiError("unexpected response shape", retryable=True)
    return data


def _extract_text(data: Mapping[str, Any]) -> str:
    try:
        candidate = data["candidates"][0]
        parts = candidate["content"]["parts"]
    except (KeyError, IndexError, TypeError):
        reason = ""
        try:
            reason = f" (finishReason={data['candidates'][0].get('finishReason')})"
        except (KeyError, IndexError, TypeError, AttributeError):
            pass
        raise GeminiError("no usable content in response" + reason, retryable=True) from None
    text = "".join(
        p["text"] for p in parts if isinstance(p, dict) and isinstance(p.get("text"), str) and not p.get("thought")
    ).strip()
    if not text:
        raise GeminiError(f"empty text (finishReason={candidate.get('finishReason')})", retryable=True)
    return text


class GeminiClient:
    def __init__(
        self,
        api_key: str,
        models: str | Sequence[str],
        *,
        timeout: float = 8.0,  # per attempt
        deadline: float = 12.0,  # total time across all attempts for one request
        cooldown: float = 30.0,  # pause after every model failed
        http_post: Callable[..., Mapping[str, Any]] = _post,
        clock: Callable[[], float] = time.monotonic,
    ):
        if not api_key:
            raise ValueError("A Gemini API key is required")
        names = [models] if isinstance(models, str) else list(models)
        if not names or not all(isinstance(m, str) and _MODEL_RE.match(m) for m in names):
            raise ValueError("Invalid Gemini model name")
        self._api_key = api_key
        self._models = names
        self._timeout, self._deadline, self._cooldown = timeout, deadline, cooldown
        self._http_post, self._clock = http_post, clock
        self._paused_until = 0.0

    def generate(
        self, *, system: str, prompt: str, json_mode: bool = False, max_tokens: int = DEFAULT_MAX_TOKENS
    ) -> str:
        if self._clock() < self._paused_until:
            raise GeminiError("paused briefly after repeated failures")
        config: dict[str, Any] = {"temperature": 0.2, "maxOutputTokens": max_tokens}
        if json_mode:
            config["responseMimeType"] = "application/json"
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": config,
        }
        headers = {"x-goog-api-key": self._api_key, "Content-Type": "application/json"}

        started, last_error = self._clock(), None
        for model in self._models:
            remaining = self._deadline - (self._clock() - started)
            if remaining <= 0:
                break
            try:
                data = self._http_post(ENDPOINT.format(model=model), headers, body, min(self._timeout, remaining))
                return _extract_text(data)
            except GeminiError as err:
                if not err.retryable:
                    raise
                last_error = err
                log.warning("Gemini model %s failed (%s); trying the next one", model, err)
        self._paused_until = self._clock() + self._cooldown
        raise GeminiError(f"all models failed; last error: {last_error}")
