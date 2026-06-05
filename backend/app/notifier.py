from __future__ import annotations

import base64
import hashlib
import hmac
import time
from urllib.parse import quote_plus

import httpx

from app import automation
from app.config import get_settings
from app.database import SessionLocal


class DingTalkNotifier:
    def __init__(self, settings_data: dict | None = None) -> None:
        self.settings = get_settings()
        self.settings_data = settings_data

    def enabled(self) -> bool:
        return bool(self._webhook())

    def _settings_data(self) -> dict:
        if self.settings_data is not None:
            return self.settings_data
        db = SessionLocal()
        try:
            self.settings_data = automation.get_raw_settings(db)
            return self.settings_data
        finally:
            db.close()

    def _webhook(self) -> str:
        return str(self._settings_data().get("dingtalk_webhook") or self.settings.dingtalk_webhook or "")

    def _secret(self) -> str:
        return str(self._settings_data().get("dingtalk_secret") or self.settings.dingtalk_secret or "")

    def signed_url(self) -> str:
        webhook = self._webhook()
        secret = self._secret()
        assert webhook
        if not secret:
            return webhook
        timestamp = str(int(time.time() * 1000))
        string_to_sign = f"{timestamp}\n{secret}"
        sign = hmac.new(
            secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        separator = "&" if "?" in webhook else "?"
        return f"{webhook}{separator}timestamp={timestamp}&sign={quote_plus(base64.b64encode(sign).decode('utf-8'))}"

    def send_markdown(self, title: str, markdown_text: str) -> dict:
        if not self.enabled():
            return {"ok": False, "reason": "DingTalk webhook is not configured"}
        payload = {
            "msgtype": "markdown",
            "markdown": {"title": title, "text": markdown_text},
        }
        try:
            with httpx.Client(timeout=20) as client:
                response = client.post(self.signed_url(), json=payload)
                response.raise_for_status()
                data = response.json()
                return {"ok": data.get("errcode") == 0, "response": data}
        except Exception as exc:
            return {"ok": False, "reason": str(exc)}
