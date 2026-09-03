from src.outcome_analysis import render_report, summarize


def test_summarize_separates_lanes_and_decisions():
    records = [
        {"decision": "EARLY_BUY", "lane": "UTILITY", "utility_verified": True, "notified": True},
        {"decision": "WAIT", "lane": "HIGH_POTENTIAL", "utility_verified": False, "notified": False},
        {"decision": "NO_TRADE", "lane": "UTILITY", "utility_verified": False, "notified": False},
        {"decision": "BUY_CANDIDATE", "lane": "UTILITY", "utility_verified": True, "notified": True},
    ]
    summary = summarize(records)
    assert summary.observations == 4
    assert summary.notified == 2
    assert summary.utility_observations == 3
    assert summary.high_potential_observations == 1
    assert summary.utility_verified == 2
    assert summary.early_buys == 1
    assert summary.buy_candidates == 1
    assert summary.waits == 1
    assert summary.no_trades == 1
    assert summary.notification_rate == 0.5


def test_render_report_is_operator_readable():
    report = render_report([{"decision": "EARLY_BUY", "lane": "UTILITY", "notified": True}])
    assert "TRUTH LIVE TELEMETRY" in report
    assert "utility_observations=1" in report
    assert "early_buys=1" in report
