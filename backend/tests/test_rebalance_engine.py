import unittest
from unittest.mock import patch

import pandas as pd

from backend.engine.rebalance_engine import RebalanceEngine
from backend.models.schemas import BacktestRequest


class FakeMarketDataService:
    def __init__(self, price_df, benchmark_df):
        self.price_df = price_df
        self.benchmark_df = benchmark_df

    def get_price_data(self, stock_codes, start_date, end_date):
        codes = set(stock_codes)
        df = self.price_df[self.price_df["stock_code"].isin(codes)].copy()
        return df[
            (df["trade_date"] >= start_date)
            & (df["trade_date"] <= end_date)
        ]

    def get_benchmark_data(self, benchmark_code, start_date, end_date):
        df = self.benchmark_df[self.benchmark_df["stock_code"] == benchmark_code].copy()
        return df[
            (df["trade_date"] >= start_date)
            & (df["trade_date"] <= end_date)
        ]


class RebalanceEngineTest(unittest.TestCase):
    def test_initial_rebalance_uses_initial_capital_and_charges_buy_fee(self):
        dates = ["2015-01-05", "2015-01-06", "2015-02-02"]
        price_df = pd.DataFrame([
            {"trade_date": date, "stock_code": "510300.SH", "adj_close": 10.0}
            for date in dates
        ] + [
            {"trade_date": date, "stock_code": "510500.SH", "adj_close": 20.0}
            for date in dates
        ])
        benchmark_df = pd.DataFrame([
            {"trade_date": date, "stock_code": "000001.SH", "adj_close": 100.0 + index}
            for index, date in enumerate(dates)
        ])
        fake_service = FakeMarketDataService(price_df, benchmark_df)
        request = BacktestRequest(
            etf_list=[
                {"stock_code": "510300.SH", "weight": 0.5},
                {"stock_code": "510500.SH", "weight": 0.5},
            ],
            start_date="2015-01-01",
            end_date="2015-02-28",
            rebalance_freq="month_start",
            initial_capital=100000.0,
            buy_fee_rate=0.0003,
            sell_fee_rate=0.0003,
            benchmark_code="000001.SH",
        )

        with patch("backend.engine.rebalance_engine.market_data_service", fake_service):
            result = RebalanceEngine().run_backtest(request)

        first_net_value = result.net_value_series[0]["net_value"]
        self.assertAlmostEqual(first_net_value, 1 / 1.0003, places=8)
        self.assertGreater(result.metrics["final_value"], 0)
        self.assertEqual(result.metrics["rebalance_count"], 2)
        self.assertEqual(len(result.benchmark_series), 3)
        self.assertEqual(set(result.asset_return_series), {"510300.SH", "510500.SH"})
        self.assertEqual(len(result.asset_return_series["510300.SH"]), 3)

    def test_missing_pre_listing_price_uses_cash_instead_of_proxy(self):
        dates = [
            "2017-08-21",
            "2017-08-22",
            "2017-08-23",
            "2017-08-24",
            "2017-08-25",
        ]
        price_df = pd.DataFrame([
            {"trade_date": "2017-08-24", "stock_code": "511260.SH", "adj_close": 10.0},
            {"trade_date": "2017-08-25", "stock_code": "511260.SH", "adj_close": 10.1},
        ])
        benchmark_df = pd.DataFrame([
            {"trade_date": date, "stock_code": "000001.SH", "adj_close": 3000.0 + index}
            for index, date in enumerate(dates)
        ])
        fake_service = FakeMarketDataService(price_df, benchmark_df)
        request = BacktestRequest(
            etf_list=[{"stock_code": "511260.SH", "weight": 1.0}],
            start_date="2017-08-21",
            end_date="2017-08-25",
            rebalance_freq="month_start",
            initial_capital=100000.0,
            buy_fee_rate=0.0003,
            sell_fee_rate=0.0003,
            benchmark_code="000001.SH",
        )

        with patch("backend.engine.rebalance_engine.market_data_service", fake_service):
            result = RebalanceEngine().run_backtest(request)

        first_record = result.rebalance_records[0]
        holding = first_record["holdings"]["511260.SH"]
        self.assertEqual(holding["effective_code"], "511260.SH")
        self.assertTrue(holding["cash_substitute"])
        self.assertEqual(holding["shares"], 0.0)
        self.assertEqual(first_record["cash_after"], 100000.0)
        self.assertEqual(first_record["trades"]["511260.SH"]["buy_value"], 0.0)
        self.assertTrue(any("2017-08-24 前无行情" in warning for warning in result.warnings))
        self.assertFalse(any("511010.SH" in warning for warning in result.warnings))
        self.assertTrue(all(item["net_value"] == 1.0 for item in result.net_value_series))
        self.assertIn("511260.SH", result.asset_return_series)
        self.assertEqual(len(result.asset_return_series["511260.SH"]), 2)

    def test_etf_with_no_price_data_uses_cash_for_whole_period(self):
        dates = ["2024-01-02", "2024-01-03", "2024-01-04"]
        price_df = pd.DataFrame(columns=["trade_date", "stock_code", "adj_close"])
        benchmark_df = pd.DataFrame([
            {"trade_date": date, "stock_code": "000001.SH", "adj_close": 3000.0 + index}
            for index, date in enumerate(dates)
        ])
        fake_service = FakeMarketDataService(price_df, benchmark_df)
        request = BacktestRequest(
            etf_list=[{"stock_code": "588999.SH", "weight": 1.0}],
            start_date="2024-01-02",
            end_date="2024-01-04",
            rebalance_freq="week_start",
            initial_capital=100000.0,
            buy_fee_rate=0.0003,
            sell_fee_rate=0.0003,
            benchmark_code="000001.SH",
        )

        with patch("backend.engine.rebalance_engine.market_data_service", fake_service):
            result = RebalanceEngine().run_backtest(request)

        self.assertTrue(any("全程使用现金替代" in warning for warning in result.warnings))
        self.assertEqual(result.rebalance_records[0]["cash_after"], 100000.0)
        self.assertTrue(result.rebalance_records[0]["holdings"]["588999.SH"]["cash_substitute"])
        self.assertEqual(result.asset_return_series["588999.SH"], [])
        self.assertTrue(all(item["net_value"] == 1.0 for item in result.net_value_series))

    def test_no_rebalance_only_builds_position_on_first_trading_day(self):
        dates = ["2024-01-02", "2024-01-03", "2024-02-01"]
        price_df = pd.DataFrame([
            {"trade_date": "2024-01-02", "stock_code": "510300.SH", "adj_close": 10.0},
            {"trade_date": "2024-01-03", "stock_code": "510300.SH", "adj_close": 20.0},
            {"trade_date": "2024-02-01", "stock_code": "510300.SH", "adj_close": 20.0},
            {"trade_date": "2024-01-02", "stock_code": "510500.SH", "adj_close": 20.0},
            {"trade_date": "2024-01-03", "stock_code": "510500.SH", "adj_close": 10.0},
            {"trade_date": "2024-02-01", "stock_code": "510500.SH", "adj_close": 10.0},
        ])
        benchmark_df = pd.DataFrame([
            {"trade_date": date, "stock_code": "000001.SH", "adj_close": 3000.0 + index}
            for index, date in enumerate(dates)
        ])
        fake_service = FakeMarketDataService(price_df, benchmark_df)
        request = BacktestRequest(
            etf_list=[
                {"stock_code": "510300.SH", "weight": 0.5},
                {"stock_code": "510500.SH", "weight": 0.5},
            ],
            start_date="2024-01-02",
            end_date="2024-02-01",
            rebalance_freq="none",
            initial_capital=100000.0,
            buy_fee_rate=0.0003,
            sell_fee_rate=0.0003,
            benchmark_code="000001.SH",
        )

        with patch("backend.engine.rebalance_engine.market_data_service", fake_service):
            result = RebalanceEngine().run_backtest(request)

        self.assertEqual(result.metrics["rebalance_count"], 1)
        self.assertEqual(len(result.rebalance_records), 1)
        self.assertEqual(result.rebalance_records[0]["date"], "2024-01-02")
        self.assertGreater(result.net_value_series[-1]["net_value"], result.net_value_series[0]["net_value"])


if __name__ == "__main__":
    unittest.main()
