from __future__ import annotations

import json
from typing import Any

import httpx

from app.config import get_settings


class LLMClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    def enabled(self) -> bool:
        return bool(self.settings.llm_base_url and self.settings.llm_api_key and self.settings.llm_model)

    def _chat(self, messages: list[dict[str, str]], response_format: dict[str, str] | None = None) -> str | None:
        if not self.enabled():
            return None
        assert self.settings.llm_base_url
        assert self.settings.llm_api_key
        assert self.settings.llm_model
        url = f"{self.settings.llm_base_url.rstrip('/')}/chat/completions"
        payload: dict[str, Any] = {
            "model": self.settings.llm_model,
            "messages": messages,
            "temperature": 0.4,
        }
        if response_format:
            payload["response_format"] = response_format
        headers = {
            "Authorization": f"Bearer {self.settings.llm_api_key}",
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(timeout=90) as client:
                response = client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"]
        except Exception:
            return None

    def json_chat(
        self,
        system: str,
        user: str,
        fallback: dict[str, Any],
    ) -> dict[str, Any]:
        content = self._chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format={"type": "json_object"},
        )
        if not content:
            return fallback
        try:
            data = json.loads(content)
            return data if isinstance(data, dict) else fallback
        except json.JSONDecodeError:
            return fallback

    def text_chat(self, system: str, user: str, fallback: str) -> str:
        content = self._chat([{"role": "system", "content": system}, {"role": "user", "content": user}])
        return content.strip() if content and content.strip() else fallback

