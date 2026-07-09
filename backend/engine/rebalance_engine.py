import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
from ..models.schemas import BacktestRequest, BacktestResult, normalize_stock_code
from ..data.market_data import market_data_service
from ..utils.date_utils import get_rebalance_dates, normalize_weights


class RebalanceEngine:
    """ETF再均衡回测引擎"""

    def run_backtest(self, request: BacktestRequest) -> BacktestResult:
        """
        执行再均衡回测。

        交易假设：
        - 使用日收盘价成交。
        - 再均衡日在目标日期的收盘价调仓。
        - 买入和卖出费用分别按成交金额线性扣除。
        """
        raw_codes = [item.stock_code for item in request.etf_list]
        if len(set(raw_codes)) != len(raw_codes):
            raise ValueError("ETF代码不能重复")

        weights_dict = {item.stock_code: item.weight for item in request.etf_list}
        stock_codes = list(weights_dict.keys())
        weights = normalize_weights(list(weights_dict.values()))
        weights_dict = dict(zip(stock_codes, weights))
        benchmark_weights_dict = {
            item.stock_code: item.weight
            for item in request.benchmark_list
        }
        if len(benchmark_weights_dict) != len(request.benchmark_list):
            raise ValueError("基准代码不能重复")

        price_df = market_data_service.get_price_data(
            stock_codes,
            request.start_date,
            request.end_date
        )
        benchmark_df = market_data_service.get_price_data(
            list(benchmark_weights_dict.keys()),
            request.start_date,
            request.end_date,
        )

        trading_dates = self._build_trading_dates(
            price_df,
            benchmark_df,
            request.start_date,
            request.end_date,
        )
        price_pivot = self._build_price_pivot(price_df, trading_dates)

        logical_prices, warnings = self._build_logical_price_pivot(
            price_pivot,
            stock_codes
        )
        logical_prices = logical_prices.sort_index()
        logical_prices = self._forward_fill_missing_prices(logical_prices, warnings)
        asset_return_series = self._build_asset_return_series(logical_prices, stock_codes)

        rebalance_dates = set(get_rebalance_dates(
            [str(date) for date in trading_dates],
            request.rebalance_freq
        ))

        net_values, rebalance_records = self._run_rebalance_loop(
            logical_prices=logical_prices,
            stock_codes=stock_codes,
            weights_dict=weights_dict,
            rebalance_dates=rebalance_dates,
            base_value=1.0,
            buy_fee_rate=request.buy_fee_rate,
            sell_fee_rate=request.sell_fee_rate,
        )

        benchmark_series, benchmark_warnings = self._build_benchmark_series(
            benchmark_weights=benchmark_weights_dict,
            start_date=request.start_date,
            end_date=request.end_date,
            trading_dates=trading_dates,
            benchmark_df=benchmark_df,
        )
        warnings.extend(benchmark_warnings)

        metrics = self._calculate_metrics(
            net_values,
            rebalance_count=len(rebalance_records)
        )
        benchmark_metrics = self._calculate_metrics(
            benchmark_series,
            rebalance_count=0
        ) if benchmark_series else {}

        return BacktestResult(
            net_value_series=net_values,
            benchmark_series=benchmark_series,
            asset_return_series=asset_return_series,
            metrics=metrics,
            benchmark_metrics=benchmark_metrics,
            rebalance_records=rebalance_records,
            warnings=warnings,
        )

    def _build_trading_dates(
        self,
        price_df: pd.DataFrame,
        benchmark_df: pd.DataFrame,
        start_date: str,
        end_date: str,
    ) -> List[str]:
        dates = []
        for df in (price_df, benchmark_df):
            if df is None or df.empty or "trade_date" not in df.columns:
                continue
            parsed = pd.to_datetime(df["trade_date"], errors="coerce").dropna()
            dates.extend(parsed.dt.strftime("%Y-%m-%d").tolist())

        if not dates:
            return [
                date.strftime("%Y-%m-%d")
                for date in pd.bdate_range(start=start_date, end=end_date)
            ]

        return sorted(dict.fromkeys(dates))

    def _build_price_pivot(self, price_df: pd.DataFrame, trading_dates: List[str]) -> pd.DataFrame:
        if (
            price_df is None
            or price_df.empty
            or not {"trade_date", "stock_code", "adj_close"}.issubset(price_df.columns)
        ):
            return pd.DataFrame(index=trading_dates)

        price_pivot = price_df.pivot_table(
            index="trade_date",
            columns="stock_code",
            values="adj_close",
            aggfunc="last"
        ).sort_index()
        price_pivot.index = pd.to_datetime(price_pivot.index).strftime("%Y-%m-%d")
        return price_pivot.reindex(trading_dates)

    def _build_logical_price_pivot(
        self,
        raw_prices: pd.DataFrame,
        stock_codes: List[str]
    ) -> Tuple[pd.DataFrame, List[str]]:
        logical_prices = pd.DataFrame(index=raw_prices.index)
        warnings = []

        for code in stock_codes:
            if code in raw_prices.columns:
                series = raw_prices[code]
            else:
                series = pd.Series(index=raw_prices.index, dtype=float)

            logical_prices[code] = series
            available_prices = series.dropna()
            if available_prices.empty:
                warnings.append(f"{code} 在回测区间内无行情，对应目标权重全程使用现金替代")
                continue

            first_date = str(available_prices.index[0])
            first_backtest_date = str(raw_prices.index[0])
            if first_date > first_backtest_date:
                warnings.append(f"{code} 在 {first_date} 前无行情，对应目标权重使用现金替代")

        return logical_prices, warnings

    def _forward_fill_missing_prices(
        self,
        prices: pd.DataFrame,
        warnings: List[str]
    ) -> pd.DataFrame:
        filled = prices.copy()
        filled_details = []
        for code in prices.columns:
            first_valid_index = prices[code].first_valid_index()
            if first_valid_index is None:
                continue
            post_listing = prices.loc[first_valid_index:, code]
            missing_count = int(post_listing.isna().sum())
            if missing_count > 0:
                filled.loc[first_valid_index:, code] = post_listing.ffill()
                filled_details.append(f"{code} {missing_count}天")

        if filled_details:
            warnings.append("部分ETF有行情后仍缺失收盘价，已使用前一有效收盘价估值: " + ", ".join(filled_details))
        return filled

    def _run_rebalance_loop(
        self,
        logical_prices: pd.DataFrame,
        stock_codes: List[str],
        weights_dict: Dict[str, float],
        rebalance_dates: set,
        base_value: float,
        buy_fee_rate: float,
        sell_fee_rate: float,
    ) -> Tuple[List[dict], List[dict]]:
        cash = base_value
        holdings = {code: 0.0 for code in stock_codes}
        net_values = []
        rebalance_records = []

        for date in logical_prices.index:
            date_str = str(date)
            current_prices = logical_prices.loc[date]

            if date_str in rebalance_dates:
                record = self._rebalance_on_date(
                    date_str=date_str,
                    current_prices=current_prices,
                    stock_codes=stock_codes,
                    weights_dict=weights_dict,
                    holdings=holdings,
                    cash=cash,
                    buy_fee_rate=buy_fee_rate,
                    sell_fee_rate=sell_fee_rate,
                )
                cash = record["cash_after"]
                holdings = {
                    code: record["holdings"][code]["shares"]
                    for code in stock_codes
                }
                rebalance_records.append(record)

            portfolio_value = self._portfolio_value(cash, holdings, current_prices, stock_codes)
            net_values.append({
                "date": date_str,
                "net_value": float(portfolio_value / base_value),
            })

        return net_values, rebalance_records

    def _rebalance_on_date(
        self,
        date_str: str,
        current_prices: pd.Series,
        stock_codes: List[str],
        weights_dict: Dict[str, float],
        holdings: Dict[str, float],
        cash: float,
        buy_fee_rate: float,
        sell_fee_rate: float,
    ) -> dict:
        portfolio_value_before = self._portfolio_value(cash, holdings, current_prices, stock_codes)
        available_prices = {
            code: self._has_valid_price(current_prices[code])
            for code in stock_codes
        }
        current_values = {
            code: holdings[code] * float(current_prices[code]) if available_prices[code] else 0.0
            for code in stock_codes
        }
        target_values = {
            code: portfolio_value_before * weights_dict[code] if available_prices[code] else 0.0
            for code in stock_codes
        }

        trades = {
            code: {
                "sell_value": 0.0,
                "buy_value": 0.0,
                "sell_fee": 0.0,
                "buy_fee": 0.0,
            }
            for code in stock_codes
        }
        total_fee = 0.0
        turnover = 0.0

        for code in stock_codes:
            if not available_prices[code]:
                continue
            price = float(current_prices[code])
            sell_value = max(current_values[code] - target_values[code], 0.0)
            if sell_value <= 0:
                continue
            sell_shares = sell_value / price
            fee = sell_value * sell_fee_rate
            holdings[code] -= sell_shares
            cash += sell_value - fee
            trades[code]["sell_value"] = sell_value
            trades[code]["sell_fee"] = fee
            total_fee += fee
            turnover += sell_value

        buy_requests = {
            code: max(target_values[code] - current_values[code], 0.0) if available_prices[code] else 0.0
            for code in stock_codes
        }
        requested_cash = sum(value * (1.0 + buy_fee_rate) for value in buy_requests.values())
        buy_scale = min(1.0, cash / requested_cash) if requested_cash > 0 else 1.0

        for code in stock_codes:
            if not available_prices[code]:
                continue
            price = float(current_prices[code])
            buy_value = buy_requests[code] * buy_scale
            if buy_value <= 0:
                continue
            fee = buy_value * buy_fee_rate
            holdings[code] += buy_value / price
            cash -= buy_value + fee
            trades[code]["buy_value"] = buy_value
            trades[code]["buy_fee"] = fee
            total_fee += fee
            turnover += buy_value

        holdings_detail = {}
        for code in stock_codes:
            if available_prices[code]:
                price = float(current_prices[code])
                value = holdings[code] * price
            else:
                price = 0.0
                value = 0.0
            holdings_detail[code] = {
                "effective_code": code,
                "target_weight": float(weights_dict[code]),
                "shares": float(holdings[code]),
                "price": price,
                "value": float(value),
                "cash_substitute": not available_prices[code],
            }

        portfolio_value_after = self._portfolio_value(cash, holdings, current_prices, stock_codes)
        return {
            "date": date_str,
            "capital_before": float(portfolio_value_before),
            "capital_after": float(portfolio_value_after),
            "cash_after": float(cash),
            "turnover": float(turnover),
            "fee": float(total_fee),
            "holdings": holdings_detail,
            "trades": trades,
        }

    def _portfolio_value(
        self,
        cash: float,
        holdings: Dict[str, float],
        current_prices: pd.Series,
        stock_codes: List[str]
    ) -> float:
        return float(cash + sum(
            holdings[code] * float(current_prices[code])
            for code in stock_codes
            if self._has_valid_price(current_prices[code])
        ))

    def _has_valid_price(self, price) -> bool:
        return pd.notna(price) and float(price) > 0

    def _build_benchmark_series(
        self,
        benchmark_weights: Dict[str, float],
        start_date: str,
        end_date: str,
        trading_dates: List[str],
        benchmark_df: pd.DataFrame | None = None,
    ) -> Tuple[List[dict], List[str]]:
        warnings = []
        benchmark_codes = list(benchmark_weights.keys())
        if not benchmark_codes:
            warnings.append("未选择基准指数，未生成基准曲线")
            return [], warnings

        if benchmark_df is None:
            benchmark_df = market_data_service.get_price_data(
                benchmark_codes,
                start_date,
                end_date
            )
        if benchmark_df.empty:
            warnings.append("所选基准指数无行情，未生成基准曲线")
            return [], warnings

        benchmark_pivot = benchmark_df.pivot_table(
            index="trade_date",
            columns="stock_code",
            values="adj_close",
            aggfunc="last"
        ).sort_index()

        benchmark_pivot.index = pd.to_datetime(benchmark_pivot.index).strftime("%Y-%m-%d")
        benchmark_pivot = benchmark_pivot.reindex(trading_dates)

        missing_codes = [
            code for code in benchmark_codes
            if code not in benchmark_pivot.columns or benchmark_pivot[code].dropna().empty
        ]
        if missing_codes:
            warnings.append(f"基准 {', '.join(missing_codes)} 无行情，未生成基准曲线")
            return [], warnings

        filled_prices = pd.DataFrame(index=benchmark_pivot.index)
        for code in benchmark_codes:
            prices = pd.to_numeric(benchmark_pivot[code], errors="coerce")
            prices = prices.where(prices > 0)
            first_valid_index = prices.first_valid_index()
            if first_valid_index is None:
                warnings.append(f"基准 {code} 与策略交易日无交集，未生成基准曲线")
                return [], warnings
            filled = prices.copy()
            filled.loc[first_valid_index:] = filled.loc[first_valid_index:].ffill()
            filled_prices[code] = filled

        complete_prices = filled_prices.dropna()
        if complete_prices.empty:
            warnings.append("所选基准指数没有共同行情日期，未生成基准曲线")
            return [], warnings

        common_start = complete_prices.index[0]
        base_prices = complete_prices.loc[common_start]
        if (base_prices <= 0).any():
            warnings.append("所选基准指数共同首日价格无效，未生成基准曲线")
            return [], warnings

        normalized = complete_prices.loc[common_start:].divide(base_prices)
        weighted_series = normalized.mul(pd.Series(benchmark_weights), axis=1).sum(axis=1)

        return [
            {"date": str(date), "net_value": float(net_value)}
            for date, net_value in weighted_series.items()
            if pd.notna(net_value)
        ], warnings

    def _build_asset_return_series(
        self,
        logical_prices: pd.DataFrame,
        stock_codes: List[str],
    ) -> dict:
        series_by_asset = {}
        for code in stock_codes:
            prices = logical_prices[code].dropna()
            if prices.empty:
                series_by_asset[code] = []
                continue

            first_price = float(prices.iloc[0])
            if first_price <= 0:
                series_by_asset[code] = []
                continue

            series_by_asset[code] = [
                {"date": str(date), "net_value": float(price / first_price)}
                for date, price in prices.items()
            ]
        return series_by_asset

    def _calculate_metrics(
        self,
        net_values: List[dict],
        rebalance_count: int
    ) -> dict:
        """计算回测指标"""
        if not net_values:
            return {}

        nv_df = pd.DataFrame(net_values)
        nv_series = pd.Series(nv_df["net_value"].to_numpy(dtype=float))

        total_return = (nv_series.iloc[-1] - 1.0) * 100

        dates = pd.to_datetime(nv_df["date"])
        elapsed_days = max((dates.iloc[-1] - dates.iloc[0]).days, 1)
        years = elapsed_days / 365.25
        annual_return = ((nv_series.iloc[-1] ** (1 / years)) - 1) * 100 if years > 0 else 0

        cummax = nv_series.cummax()
        drawdown = (nv_series - cummax) / cummax
        max_drawdown = drawdown.min() * 100

        returns = nv_series.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
        volatility = returns.std() * np.sqrt(252) * 100 if not returns.empty else 0

        risk_free_rate = 0.03
        if volatility > 0:
            sharpe_ratio = (annual_return / 100 - risk_free_rate) / (volatility / 100)
        else:
            sharpe_ratio = 0

        return {
            "total_return": float(total_return),
            "annual_return": float(annual_return),
            "max_drawdown": float(max_drawdown),
            "volatility": float(volatility),
            "sharpe_ratio": float(sharpe_ratio),
            "final_net_value": float(nv_series.iloc[-1]),
            "rebalance_count": int(rebalance_count),
        }


rebalance_engine = RebalanceEngine()
