from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd

from .models import BacktestRequest


EPSILON = 1e-8


@dataclass
class Trade:
    date: pd.Timestamp
    code: str
    side: str
    shares: float
    price: float
    gross_value: float
    fee: float
    reason: str

    def as_dict(self) -> dict[str, object]:
        return {
            "date": self.date.strftime("%Y-%m-%d"),
            "code": self.code,
            "side": self.side,
            "shares": round(self.shares, 4),
            "price": round(self.price, 4),
            "gross_value": round(self.gross_value, 2),
            "fee": round(self.fee, 2),
            "reason": self.reason,
        }


def build_price_frame(histories: dict[str, pd.DataFrame]) -> pd.DataFrame:
    frames: list[pd.Series] = []
    for code, history in histories.items():
        if history.empty:
            raise ValueError(f"{code} 没有可用价格数据")
        series = history.copy()
        series["date"] = pd.to_datetime(series["date"])
        series = series.dropna(subset=["date", "close"]).drop_duplicates("date").set_index("date")["close"]
        frames.append(series.rename(code))
    prices = pd.concat(frames, axis=1).sort_index().ffill().dropna(how="any")
    if len(prices) < 2:
        raise ValueError("共同交易日不足，无法回测")
    return prices.astype(float)


def _period_key(date: pd.Timestamp, frequency: str) -> str:
    base_frequency = frequency.removesuffix("_end")
    if base_frequency == "weekly":
        year, week, _ = date.isocalendar()
        return f"{year}-{week}"
    if base_frequency == "quarterly":
        return f"{date.year}-Q{date.quarter}"
    return date.strftime("%Y-%m")


def _period_starts(index: pd.DatetimeIndex, frequency: str) -> set[pd.Timestamp]:
    starts = {index[0]}
    previous = _period_key(index[0], frequency)
    for date in index[1:]:
        current = _period_key(date, frequency)
        if current != previous:
            starts.add(date)
            previous = current
    return starts


def _period_ends(index: pd.DatetimeIndex, frequency: str) -> set[pd.Timestamp]:
    if index.empty:
        return set()
    ends: set[pd.Timestamp] = set()
    previous_date = index[0]
    previous_key = _period_key(previous_date, frequency)
    for date in index[1:]:
        current_key = _period_key(date, frequency)
        if current_key != previous_key:
            ends.add(previous_date)
            previous_key = current_key
        previous_date = date
    ends.add(previous_date)
    return ends


def _period_dates(index: pd.DatetimeIndex, frequency: str) -> set[pd.Timestamp]:
    return _period_ends(index, frequency) if frequency.endswith("_end") else _period_starts(index, frequency)


def _record_trade(
    trades: list[Trade],
    date: pd.Timestamp,
    code: str,
    side: str,
    shares: float,
    price: float,
    fee_rate: float,
    reason: str,
) -> float:
    gross_value = shares * price
    fee = gross_value * fee_rate
    trades.append(Trade(date, code, side, shares, price, gross_value, fee, reason))
    return fee


def _buy_by_weights(
    date: pd.Timestamp,
    total_budget: float,
    prices: pd.Series,
    weights: dict[str, float],
    shares: dict[str, float],
    fee_rate: float,
    trades: list[Trade],
    reason: str,
) -> tuple[float, float]:
    """Spend up to total_budget, including fees; returns leftover cash and paid fees."""
    cash = total_budget
    fees = 0.0
    for code, weight in weights.items():
        gross_value = total_budget * weight / (1 + fee_rate)
        quantity = gross_value / float(prices[code])
        if quantity <= EPSILON:
            continue
        fee = _record_trade(trades, date, code, "buy", quantity, float(prices[code]), fee_rate, reason)
        shares[code] += quantity
        cash -= gross_value + fee
        fees += fee
    return max(cash, 0.0), fees


def _rebalance(
    date: pd.Timestamp,
    prices: pd.Series,
    weights: dict[str, float],
    shares: dict[str, float],
    cash: float,
    fee_rate: float,
    trades: list[Trade],
    reason: str,
) -> tuple[float, float]:
    """Move current portfolio near its target weights while retaining fee-aware cash."""
    before_value = cash + sum(shares[code] * float(prices[code]) for code in weights)
    target_values = {code: before_value * weight for code, weight in weights.items()}
    fees = 0.0

    for code in weights:
        price = float(prices[code])
        current_value = shares[code] * price
        amount_to_sell = max(current_value - target_values[code], 0.0)
        if amount_to_sell <= EPSILON:
            continue
        quantity = min(shares[code], amount_to_sell / price)
        fee = _record_trade(trades, date, code, "sell", quantity, price, fee_rate, reason)
        shares[code] -= quantity
        cash += quantity * price - fee
        fees += fee

    buy_needs = {
        code: max(target_values[code] - shares[code] * float(prices[code]), 0.0)
        for code in weights
    }
    required = sum(value * (1 + fee_rate) for value in buy_needs.values())
    scale = min(1.0, cash / required) if required > EPSILON else 0.0
    for code, desired_value in buy_needs.items():
        gross_value = desired_value * scale
        if gross_value <= EPSILON:
            continue
        price = float(prices[code])
        quantity = gross_value / price
        fee = _record_trade(trades, date, code, "buy", quantity, price, fee_rate, reason)
        shares[code] += quantity
        cash -= gross_value + fee
        fees += fee
    return max(cash, 0.0), fees


def _metric_payload(records: pd.DataFrame, trades: list[Trade]) -> dict[str, float | int | None]:
    final_value = float(records["nav"].iloc[-1])
    invested = float(records["invested"].iloc[-1])
    profit = final_value - invested
    capital_return = profit / invested if invested > EPSILON else 0.0

    returns = records["time_weighted_return"].replace([np.inf, -np.inf], np.nan).dropna()
    twr = float((1 + returns).prod() - 1) if not returns.empty else 0.0
    elapsed_days = max((records.index[-1] - records.index[0]).days, 1)
    annualized = (1 + twr) ** (365.25 / elapsed_days) - 1 if twr > -1 else -1.0
    volatility = float(returns.std(ddof=0) * np.sqrt(252)) if len(returns) > 1 else 0.0
    sharpe = float(returns.mean() / returns.std(ddof=0) * np.sqrt(252)) if returns.std(ddof=0) > EPSILON else None
    drawdown = records["nav"] / records["nav"].cummax() - 1
    fees = sum(trade.fee for trade in trades)

    return {
        "final_value": round(final_value, 2),
        "invested_capital": round(invested, 2),
        "profit": round(profit, 2),
        "capital_return": round(capital_return, 6),
        "time_weighted_return": round(twr, 6),
        "annualized_return": round(float(annualized), 6),
        "max_drawdown": round(float(drawdown.min()), 6),
        "annualized_volatility": round(volatility, 6),
        "sharpe": round(sharpe, 4) if sharpe is not None else None,
        "total_fees": round(fees, 2),
        "trade_count": len(trades),
        "trading_days": int(len(records)),
    }


def run_backtest(request: BacktestRequest, prices: pd.DataFrame) -> dict[str, object]:
    codes = [holding.code.strip() for holding in request.holdings]
    missing = [code for code in codes if code not in prices.columns]
    if missing:
        raise ValueError(f"缺少行情：{', '.join(missing)}")
    prices = prices.loc[:, codes].copy()
    weights_raw = {holding.code.strip(): holding.weight for holding in request.holdings}
    weight_total = sum(weights_raw.values())
    weights = {code: value / weight_total for code, value in weights_raw.items()}

    rebalance_dates = (
        _period_dates(prices.index, request.rebalance_frequency)
        if request.rebalance_frequency != "none"
        else set()
    )
    dca_dates = _period_dates(prices.index, request.dca_frequency)
    shares = {code: 0.0 for code in codes}
    cash = 0.0
    invested = 0.0
    trades: list[Trade] = []
    records: list[dict[str, float | pd.Timestamp]] = []
    previous_nav: float | None = None

    for position, (date, row) in enumerate(prices.iterrows()):
        fees_today = 0.0
        external_flow = 0.0

        if position == 0 and request.initial_capital > EPSILON:
            cash += request.initial_capital
            invested += request.initial_capital
            external_flow += request.initial_capital
            if request.strategy == "rebalance":
                cash, fees = _rebalance(
                    date, row, weights, shares, cash, request.fee_rate, trades, "初始建仓"
                )
            else:
                cash, fees = _buy_by_weights(
                    date, cash, row, weights, shares, request.fee_rate, trades, "初始投入"
                )
            fees_today += fees

        if request.strategy == "rebalance" and date in rebalance_dates and position > 0:
            cash, fees = _rebalance(
                date, row, weights, shares, cash, request.fee_rate, trades, "定期再平衡"
            )
            fees_today += fees

        if request.strategy == "dca" and date in dca_dates:
            if request.dca_mode == "amount":
                cash += request.dca_value
                invested += request.dca_value
                external_flow += request.dca_value
                leftover, fees = _buy_by_weights(
                    date,
                    request.dca_value,
                    row,
                    weights,
                    shares,
                    request.fee_rate,
                    trades,
                    "金额定投",
                )
                cash = cash - request.dca_value + leftover
                fees_today += fees
            else:
                for code in codes:
                    price = float(row[code])
                    quantity = request.dca_value
                    gross_value = quantity * price
                    fee = _record_trade(
                        trades, date, code, "buy", quantity, price, request.fee_rate, "份额定投"
                    )
                    contribution = gross_value + fee
                    shares[code] += quantity
                    invested += contribution
                    external_flow += contribution
                    fees_today += fee

            if request.rebalance_frequency != "none" and date in rebalance_dates:
                cash, fees = _rebalance(
                    date, row, weights, shares, cash, request.fee_rate, trades, "定投后再平衡"
                )
                fees_today += fees

        nav = cash + sum(shares[code] * float(row[code]) for code in codes)
        time_weighted_return = (
            nav / (previous_nav + external_flow) - 1
            if previous_nav is not None and previous_nav + external_flow > EPSILON
            else 0.0
        )
        records.append(
            {
                "date": date,
                "nav": nav,
                "cash": cash,
                "invested": invested,
                "fees": fees_today,
                "time_weighted_return": time_weighted_return,
            }
        )
        previous_nav = nav

    results = pd.DataFrame(records).set_index("date")
    final_nav = float(results["nav"].iloc[-1])
    allocation = []
    final_prices = prices.iloc[-1]
    relative_navs = {
        code: prices[code] / float(prices[code].iloc[0])
        for code in codes
    }
    fund_nav_items = []
    for holding in request.holdings:
        code = holding.code.strip()
        value = shares[code] * float(final_prices[code])
        relative_nav = relative_navs[code]
        fund_nav_items.append(
            {
                "code": code,
                "name": holding.name or code,
                "values": [round(float(value), 6) for value in relative_nav],
            }
        )
        allocation.append(
            {
                "code": code,
                "name": holding.name or code,
                "target_weight": round(weights[code], 6),
                "actual_weight": round(value / final_nav, 6) if final_nav > EPSILON else 0.0,
                "relative_nav": round(float(relative_nav.iloc[-1]), 6),
                "period_return": round(float(relative_nav.iloc[-1] - 1), 6),
                "shares": round(shares[code], 4),
                "value": round(value, 2),
            }
        )
    if cash > EPSILON:
        allocation.append(
            {
                "code": "CASH",
                "name": "现金",
                "target_weight": 0.0,
                "actual_weight": round(cash / final_nav, 6) if final_nav > EPSILON else 0.0,
                "relative_nav": None,
                "period_return": None,
                "shares": 0.0,
                "value": round(cash, 2),
            }
        )

    return {
        "metrics": _metric_payload(results, trades),
        "series": {
            "dates": [date.strftime("%Y-%m-%d") for date in results.index],
            "nav": [round(float(value), 2) for value in results["nav"]],
            "invested": [round(float(value), 2) for value in results["invested"]],
            "drawdown": [round(float(value), 6) for value in (results["nav"] / results["nav"].cummax() - 1)],
            "fund_nav": {
                "base_date": results.index[0].strftime("%Y-%m-%d"),
                "items": fund_nav_items,
            },
        },
        "allocation": allocation,
        "trades": [trade.as_dict() for trade in reversed(trades)],
        "normalized_weights": weights,
    }
