"""Minimal Gemini REST client. The API key goes in a header and is never logged."""
from __future__ import annotations

import re
from typing import Any, Callable, Mapping

import requests

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
_MODEL_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class GeminiError(Exception):
    """Any failure talking to Gemini. Callers fall back to rule-based output."""


def _post(url: str, headers: Mapping[str, str], body: Mapping[str, Any], timeout: float) -> Mapping[str, Any]:
    try:
        response = requests.post(url, headers=headers, json=body, timeout=timeout)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError):
        raise GeminiError("Gemini request failed") from None
    if not isinstance(data, dict):
        raise GeminiError("Unexpected Gemini response")
    return data


class GeminiClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        timeout: float = 8.0,
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

    def generate(self, *, system: str, prompt: str, json_mode: bool = False, max_tokens: int = 1024) -> str:
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
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError):
            raise GeminiError("Gemini returned no usable text") from None
        if not isinstance(text, str) or not text.strip():
            raise GeminiError("Gemini returned empty text")
        return text.strip()
