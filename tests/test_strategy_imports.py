from src.models import Decision, MarketCapZone


def test_new_strategy_enums_exist() -> None:
    assert Decision.EARLY_BUY.value == "EARLY_BUY"
    assert Decision.MISSED_ENTRY.value == "MISSED_ENTRY"
    assert MarketCapZone.EARLY_BUY.value == "EARLY_BUY"
    assert MarketCapZone.LATE_CONFIRMATION.value == "LATE_CONFIRMATION"
