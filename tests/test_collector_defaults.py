from src.collector import CollectorConfig


def test_collector_default_discovery_floor_is_40k() -> None:
    config = CollectorConfig()
    assert config.min_market_cap_usd == 40_000
    assert config.max_market_cap_usd == 150_000
