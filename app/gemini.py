"""Minimal Gemini REST client. The API key goes in a header and is never logged."""
from __future__ import annotations

import re
from typing import Any, Callable, Mapping

import requests

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
_MODEL_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
# Newer Gemini models spend part of this budget "thinking" before they answer, so keep it generous.
DEFAULT_MAX_TOKENS = 4096


class GeminiError(Exception):
    """Any failure talking to Gemini. Callers fall back to rule-based output."""


def _post(url: str, headers: Mapping[str, str], body: Mapping[str, Any], timeout: float) -> Mapping[str, Any]:
    try:
        response = requests.post(url, headers=headers, json=body, timeout=timeout)
    except requests.RequestException as err:
        raise GeminiError(f"network error: {type(err).__name__}") from None
    if not response.ok:
        detail = ""
        try:
            detail = str(response.json().get("error", {}).get("message", ""))[:200]
        except (ValueError, AttributeError):
            pass
        raise GeminiError(f"HTTP {response.status_code}: {detail}")
    try:
        data = response.json()
    except ValueError:
        raise GeminiError("response was not JSON") from None
    if not isinstance(data, dict):
        raise GeminiError("unexpected response shape")
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
        raise GeminiError("no usable content in response" + reason) from None
    text = "".join(
        p["text"] for p in parts if isinstance(p, dict) and isinstance(p.get("text"), str) and not p.get("thought")
    ).strip()
    if not text:
        raise GeminiError(f"empty text (finishReason={candidate.get('finishReason')})")
    return text


class GeminiClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        timeout: float = 15.0,
        http_post: Callable[..., Mapping[str, Any]] = _post,
    ):
        if not api_key:
            raise ValueError("A Gemini API key is required")
        if not _MODEL_RE.match(model):
            raise ValueError("Invalid Gemini model name")
        self._api_key = api_key
        self._url = ENDPOINT.format(model=model)
        self._timeout = timeout
        self._http_post = http_post

    def generate(
        self, *, system: str, prompt: str, json_mode: bool = False, max_tokens: int = DEFAULT_MAX_TOKENS
    ) -> str:
        config: dict[str, Any] = {"temperature": 0.2, "maxOutputTokens": max_tokens}
        if json_mode:
            config["responseMimeType"] = "application/json"
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": config,
        }
        data = self._http_post(
            self._url,
            {"x-goog-api-key": self._api_key, "Content-Type": "application/json"},
            body,
            self._timeout,
        )
        return _extract_text(data)
