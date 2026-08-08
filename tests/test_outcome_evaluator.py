from datetime import datetime, timedelta, timezone

import pytest

from src.outcome_evaluator import evaluate_outcomes


class FakeClient:
    def token_pairs(self, addresses):
        return [{"baseToken": {"address": addresses[0]}, "priceUsd": "12"}]


def test_measures_only_matured_horizon_and_is_idempotent(tmp_path):
    now = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)
    history = tmp_path / "outcomes.jsonl"
    measurements = tmp_path / "measurements.jsonl"
    history.write_text(
        '{"event_id":"e1","observed_at":"2026-08-08T10:00:00+00:00","contract_address":"MINT1",'
        '"decision":"alert","score":90,"price_usd":10}\n',
        encoding="utf-8",
    )

    first = evaluate_outcomes(history, measurements, now=now, client=FakeClient())
    second = evaluate_outcomes(history, measurements, now=now, client=FakeClient())

    assert len(first) == 1
    assert first[0].horizon_hours == 1
    assert first[0].return_pct == pytest.approx(20.0)
    assert second == []
    assert len(measurements.read_text(encoding="utf-8").splitlines()) == 1
