"""Tests for the credential-free Telegram transport boundary."""

import pytest

from src.notifier import Alert
from src.telegram import TelegramConfig, TelegramDeliveryError, TelegramNotifier


MINT = "So11111111111111111111111111111111111111112"


class FakeResponse:
    def __init__(self, data, status_code=200):
        self._data = data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("http failure")

    def json(self):
        return self._data


def test_missing_credentials_are_rejected(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    with pytest.raises(TelegramDeliveryError):
        TelegramConfig.from_env()


def test_transport_preserves_exact_contract_address():
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse({"ok": True, "result": {"message_id": 1}})

    alert = Alert(text=f"Token alert\nContract / Mint Address: {MINT}", contract_address=MINT)
    notifier = TelegramNotifier(
        TelegramConfig("123456:secret", "-100123"), post=fake_post
    )

    result = notifier.send(alert)

    assert result["ok"] is True
    assert calls[0][0].endswith("/bot123456:secret/sendMessage")
    assert calls[0][1]["json"]["chat_id"] == "-100123"
    assert MINT in calls[0][1]["json"]["text"]


def test_transport_rejects_missing_address():
    notifier = TelegramNotifier(
        TelegramConfig("123456:secret", "-100123"),
        post=lambda *args, **kwargs: FakeResponse({"ok": True}),
    )
    alert = Alert(text="Token alert", contract_address="")
    with pytest.raises(Exception):
        notifier.send(alert)


def test_telegram_rejection_is_not_reported_as_success():
    notifier = TelegramNotifier(
        TelegramConfig("123456:secret", "-100123"),
        post=lambda *args, **kwargs: FakeResponse({"ok": False, "description": "bad chat"}),
    )
    alert = Alert(text=f"Contract / Mint Address: {MINT}", contract_address=MINT)
    with pytest.raises(TelegramDeliveryError):
        notifier.send(alert)
