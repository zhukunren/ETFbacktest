from typing import List


def get_rebalance_dates(trading_dates: List[str], freq: str) -> List[str]:
    """
    根据再均衡频率获取再均衡日期

    Args:
        trading_dates: 交易日列表，格式 'YYYY-MM-DD'
        freq: 再均衡频率 none|month_start|month_end|week_start|week_end

    Returns:
        再均衡日期列表
    """
    import pandas as pd

    if not trading_dates:
        return []

    df = pd.DataFrame({'trade_date': pd.to_datetime(trading_dates)})
    df = df.sort_values('trade_date')

    rebalance_dates = []

    if freq == "none":
        # 首个交易日建仓，之后不再做再均衡。
        rebalance_dates = [df['trade_date'].iloc[0]]

    elif freq == "month_start":
        # 每月第一个交易日
        df['year_month'] = df['trade_date'].dt.to_period('M')
        rebalance_dates = df.groupby('year_month')['trade_date'].first().tolist()

    elif freq == "month_end":
        # 每月最后一个交易日
        df['year_month'] = df['trade_date'].dt.to_period('M')
        rebalance_dates = df.groupby('year_month')['trade_date'].last().tolist()

    elif freq == "week_start":
        # 每周第一个交易日
        df['year_week'] = df['trade_date'].dt.to_period('W')
        rebalance_dates = df.groupby('year_week')['trade_date'].first().tolist()

    elif freq == "week_end":
        # 每周最后一个交易日
        df['year_week'] = df['trade_date'].dt.to_period('W')
        rebalance_dates = df.groupby('year_week')['trade_date'].last().tolist()

    else:
        raise ValueError(f"Unsupported rebalance frequency: {freq}")

    return [d.strftime('%Y-%m-%d') for d in rebalance_dates]


def normalize_weights(weights: List[float]) -> List[float]:
    """权重归一化"""
    total = sum(weights)
    if total == 0:
        return weights
    return [w / total for w in weights]
