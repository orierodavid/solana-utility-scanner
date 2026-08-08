"""Tests for historical scanner outcome recording."""

import json
from datetime import datetime, timedelta, timezone

from src.models import Decision, ScoreBreakdown, TokenMarketData
from src.outcomes import AlertOutcomeRecord, JsonlOutcomeStore


MINT = "So11111111111111111111111111111111111111112"


def make_token() -> TokenMarketData:
    return TokenMarketData(
        address=MINT,
        symbol="TEST",
        name="Test Utility",
        market_cap_usd=75_000,
        liquidity_usd=25_000,
        volume_24h_usd=150_000,
        price_usd=0.001,
        holders=500,
        holder_growth_24h_pct=20,
        buy_count_24h=80,
        sell_count_24h=20,
        volume_change_24h_pct=50,
        price_change_24h_pct=20,
        token_age_hours=72,
        top_holder_concentration_pct=20,
        creator_holding_pct=5,
    )


def make_record(observed_at=None, notified=True):
    token = make_token()
    score = ScoreBreakdown(
        utility=18,
        market_structure=14,
        momentum=19,
        development=14,
        catalysts=9,
        community=8,
        risk=9,
    )
    return AlertOutcomeRecord.from_decision(
        event_id="event-1",
        token=token,
        decision=Decision.BUY_CANDIDATE,
        score=score,
        confidence=95,
        risk_overall=5,
        risk_hard_filter_failed=False,
        why_now="Verified utility and live accumulation.",
        invalidation_conditions=["Material liquidity loss"],
        wallet_intelligence_score=8.5,
        notified=notified,
        observed_at=observed_at,
    )


def test_outcome_record_preserves_exact_mint_and_score_breakdown():
    observed = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)
    record = make_record(observed)

    payload = json.loads(record.to_json())

    assert payload["contract_address"] == MINT
    assert payload["decision"] == "BUY_CANDIDATE"
    assert payload["score"] == 91
    assert payload["score_breakdown"]["utility"] == 18
    assert payload["wallet_intelligence_score"] == 8.5
    assert payload["notified"] is True


def test_jsonl_store_appends_one_complete_record(tmp_path):
    path = tmp_path / "outcomes.jsonl"
    store = JsonlOutcomeStore(path)

    store.append(make_record())

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["contract_address"] == MINT


def test_jsonl_store_detects_recent_notification_and_ignores_old_one(tmp_path):
    path = tmp_path / "outcomes.jsonl"
    store = JsonlOutcomeStore(path)
    now = datetime.now(timezone.utc)
    store.append(make_record(now - timedelta(minutes=5), notified=True))

    assert store.was_recently_notified(MINT, since=now - timedelta(hours=1)) is True
    assert store.was_recently_notified(MINT, since=now - timedelta(minutes=1)) is False


def test_outcome_record_is_observational_and_supports_non_actionable_decisions():
    token = make_token()
    score = ScoreBreakdown(
        utility=12,
        market_structure=10,
        momentum=12,
        development=10,
        catalysts=5,
        community=5,
        risk=8,
    )
    record = AlertOutcomeRecord.from_decision(
        event_id="event-2",
        token=token,
        decision=Decision.WAIT,
        score=score,
        confidence=70,
        risk_overall=20,
        risk_hard_filter_failed=False,
        why_now="Evidence is promising but not actionable.",
        notified=False,
    )

    assert record.decision is Decision.WAIT
    assert record.notified is False
    assert record.contract_address == MINT
