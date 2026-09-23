from __future__ import annotations

import pandas as pd
import pytest

from app.backtest import _period_ends, _period_starts, build_price_frame, run_backtest
from app import data
from app.models import BacktestRequest, Holding


def prices_for_two_funds() -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-02", periods=48)
    return pd.DataFrame(
        {
            "510300": [4.0 + index * 0.02 for index in range(len(dates))],
            "518880": [5.0 - index * 0.005 for index in range(len(dates))],
        },
        index=dates,
    )


def make_request(**overrides: object) -> BacktestRequest:
    payload: dict[str, object] = {
        "holdings": [
            Holding(code="510300", name="沪深300ETF", weight=60),
            Holding(code="518880", name="黄金ETF", weight=40),
        ],
        "start_date": "2024-01-01",
        "end_date": "2024-04-30",
        "initial_capital": 100_000,
        "strategy": "rebalance",
        "rebalance_frequency": "monthly",
        "fee_rate": 0.0003,
    }
    payload.update(overrides)
    return BacktestRequest(**payload)


def test_build_price_frame_aligns_histories_on_available_dates() -> None:
    dates = pd.bdate_range("2024-01-02", periods=5)
    histories = {
        "510300": pd.DataFrame({"date": dates, "close": [4.0, 4.1, 4.2, 4.3, 4.4]}),
        "518880": pd.DataFrame({"date": dates[1:], "close": [5.0, 5.1, 5.2, 5.3]}),
    }

    prices = build_price_frame(histories)

    assert prices.index[0] == dates[1]
    assert list(prices.columns) == ["510300", "518880"]


def test_quarterly_rebalance_uses_the_first_available_trading_day() -> None:
    dates = pd.DatetimeIndex(
        ["2024-01-02", "2024-03-29", "2024-04-01", "2024-06-28", "2024-07-01"]
    )

    starts = _period_starts(dates, "quarterly")

    assert starts == {pd.Timestamp("2024-01-02"), pd.Timestamp("2024-04-01"), pd.Timestamp("2024-07-01")}


def test_quarterly_rebalance_end_uses_the_last_available_trading_day() -> None:
    dates = pd.DatetimeIndex(
        ["2024-01-02", "2024-03-29", "2024-04-01", "2024-06-28", "2024-07-01"]
    )

    ends = _period_ends(dates, "quarterly_end")

    assert ends == {pd.Timestamp("2024-03-29"), pd.Timestamp("2024-06-28"), pd.Timestamp("2024-07-01")}


def test_end_of_period_frequencies_are_accepted_by_request_model() -> None:
    rebalance_request = make_request(rebalance_frequency="quarterly_end")
    dca_request = make_request(strategy="dca", dca_frequency="monthly_end")

    assert rebalance_request.rebalance_frequency == "quarterly_end"
    assert dca_request.dca_frequency == "monthly_end"


def test_periodic_rebalance_generates_initial_and_periodic_trades() -> None:
    result = run_backtest(make_request(), prices_for_two_funds())

    assert result["metrics"]["final_value"] > 0
    assert result["metrics"]["trade_count"] >= 2
    assert result["metrics"]["total_fees"] > 0
    assert result["metrics"]["invested_capital"] == 100_000
    assert any(trade["reason"] == "初始建仓" for trade in result["trades"])
    assert len(result["series"]["dates"]) == 48


def test_result_contains_a_normalized_nav_series_for_every_fund() -> None:
    prices = prices_for_two_funds()
    result = run_backtest(make_request(), prices)
    funds = {item["code"]: item for item in result["series"]["fund_nav"]["items"]}
    allocation = {item["code"]: item for item in result["allocation"]}

    assert result["series"]["fund_nav"]["base_date"] == "2024-01-02"
    assert funds["510300"]["values"][0] == 1.0
    assert funds["518880"]["values"][0] == 1.0
    assert funds["510300"]["values"][-1] == pytest.approx(prices["510300"].iloc[-1] / prices["510300"].iloc[0])
    assert allocation["510300"]["relative_nav"] == funds["510300"]["values"][-1]


def test_amount_dca_tracks_contributions_without_dropping_existing_cash() -> None:
    request = make_request(
        strategy="dca",
        initial_capital=10_000,
        dca_frequency="monthly",
        dca_mode="amount",
        dca_value=2_000,
        rebalance_frequency="none",
    )

    result = run_backtest(request, prices_for_two_funds())

    # January, February and March each make one monthly contribution. The first
    # trading day uses both the initial capital and the scheduled contribution.
    assert result["metrics"]["invested_capital"] == pytest.approx(16_000, abs=0.01)
    assert result["metrics"]["trade_count"] == 8
    assert result["metrics"]["final_value"] > 0


def test_share_dca_buys_the_requested_shares_of_each_fund() -> None:
    request = make_request(
        strategy="dca",
        initial_capital=0,
        dca_frequency="monthly",
        dca_mode="shares",
        dca_value=10,
        rebalance_frequency="none",
    )

    result = run_backtest(request, prices_for_two_funds())
    holdings = {row["code"]: row for row in result["allocation"]}

    assert holdings["510300"]["shares"] == 30
    assert holdings["518880"]["shares"] == 30
    assert result["metrics"]["invested_capital"] > 0


def test_price_cache_accepts_weekend_boundaries(monkeypatch: pytest.MonkeyPatch) -> None:
    cached = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02", "2024-03-29"]),
            "close": [3.1, 3.3],
        }
    )

    monkeypatch.setattr(data, "_read_price_cache", lambda code: cached)
    monkeypatch.setattr(
        data,
        "_download_history",
        lambda *args, **kwargs: pytest.fail("weekend-bounded cache should not download again"),
    )

    history = data.get_history("510300", "2024-01-01", "2024-03-31")

    assert list(history["close"]) == [3.1, 3.3]
