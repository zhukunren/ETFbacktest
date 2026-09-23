from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class Holding(BaseModel):
    code: str = Field(min_length=1, max_length=16)
    name: str | None = Field(default=None, max_length=80)
    weight: float = Field(gt=0, le=100)


class BacktestRequest(BaseModel):
    holdings: list[Holding] = Field(min_length=1, max_length=20)
    start_date: date
    end_date: date
    initial_capital: float = Field(default=100_000, ge=0, le=100_000_000)
    strategy: Literal["rebalance", "dca"] = "rebalance"
    rebalance_frequency: Literal[
        "none", "weekly", "weekly_end", "monthly", "monthly_end", "quarterly", "quarterly_end"
    ] = "monthly"
    dca_frequency: Literal["weekly", "weekly_end", "monthly", "monthly_end", "quarterly", "quarterly_end"] = "monthly"
    dca_mode: Literal["amount", "shares"] = "amount"
    dca_value: float = Field(default=2_000, gt=0, le=10_000_000)
    fee_rate: float = Field(default=0.0003, ge=0, le=0.03)

    @model_validator(mode="after")
    def validate_request(self) -> "BacktestRequest":
        codes = [holding.code.strip() for holding in self.holdings]
        if len(set(codes)) != len(codes):
            raise ValueError("组合中不能重复添加同一只 ETF")
        if self.start_date >= self.end_date:
            raise ValueError("结束日期必须晚于开始日期")
        if sum(holding.weight for holding in self.holdings) <= 0:
            raise ValueError("组合权重之和必须大于 0")
        return self
