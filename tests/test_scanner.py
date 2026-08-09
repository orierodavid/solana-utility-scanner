from src import scanner
from src.collector import CollectedToken, SecurityData
from src.models import TokenMarketData


MINT = "So11111111111111111111111111111111111111112"


def test_run_once_preserves_exact_contract_and_calculates_buy_pressure(monkeypatch):
    token = TokenMarketData(
        address=MINT,
        symbol="UTIL",
        name="Utility Token",
        market_cap_usd=75_000,
        liquidity_usd=20_000,
        volume_24h_usd=45_000,
        price_usd=0.00075,
        buy_count_24h=120,
        sell_count_24h=80,
        price_change_24h_pct=18.5,
        holders=250,
        top_holder_concentration_pct=18,
        mint_authority_active=False,
        freeze_authority_active=False,
    )
    security = SecurityData(
        holders=250,
        top_holder_concentration_pct=18,
        mint_authority_active=False,
        freeze_authority_active=False,
        risk_score=12,
        risk_level="Good",
        raw={},
    )

    class FakeCollector:
        def collect(self):
            return [CollectedToken(token=token, security=security, profile={"tokenAddress": MINT})]

    monkeypatch.setattr(scanner, "build_collector", lambda: FakeCollector())
    records = scanner.run_once()

    assert records[0]["contract_address"] == MINT
    assert records[0]["buy_pressure_pct"] == 60.0
    assert records[0]["price_change_24h_pct"] == 18.5
    assert records[0]["market_cap_zone"] == "EARLY_BUY"
