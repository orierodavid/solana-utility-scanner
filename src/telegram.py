"""Telegram transport for already-qualified scanner alerts.

Credentials are read only from environment variables. Nothing in this module
can turn a WAIT/NO_TRADE result into a notification.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable

import requests

from .notifier import Alert, NotificationError, telegram_payload


class TelegramDeliveryError(RuntimeError):
    """Raised when Telegram rejects or cannot receive an alert."""


@dataclass(frozen=True)
class TelegramConfig:
    bot_token: str
    chat_id: str
    api_base: str = "https://api.telegram.org"

    @classmethod
    def from_env(cls) -> "TelegramConfig":
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        if not token or not chat_id:
            raise TelegramDeliveryError(
                "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be configured before live delivery"
            )
        return cls(bot_token=token, chat_id=chat_id)


class TelegramNotifier:
    """Deliver only immutable, address-bearing Alert objects to Telegram."""

    def __init__(
        self,
        config: TelegramConfig | None = None,
        *,
        post: Callable[..., Any] = requests.post,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.config = config or TelegramConfig.from_env()
        self._post = post
        self.timeout_seconds = timeout_seconds

    def send(self, alert: Alert) -> dict[str, Any]:
        """Send one alert and return Telegram's decoded response."""
        if not isinstance(alert, Alert):
            raise NotificationError("TelegramNotifier accepts only Alert payloads")
        if not alert.contract_address or alert.contract_address not in alert.text:
            raise NotificationError("Refusing to send alert without its exact contract address")

        url = f"{self.config.api_base.rstrip('/')}/bot{self.config.bot_token}/sendMessage"
        payload = {
            "chat_id": self.config.chat_id,
            **telegram_payload(alert),
        }

        try:
            response = self._post(url, json=payload, timeout=self.timeout_seconds)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as exc:
            raise TelegramDeliveryError("Telegram delivery failed") from exc
        except ValueError as exc:
            raise TelegramDeliveryError("Telegram returned invalid JSON") from exc

        if not isinstance(data, dict) or data.get("ok") is not True:
            raise TelegramDeliveryError("Telegram rejected the alert")
        return data
