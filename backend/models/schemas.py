from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing import List, Literal, Optional
from datetime import datetime


def normalize_stock_code(stock_code: str) -> str:
    """Normalize common A-share ETF/index codes to a suffix form."""
    code = stock_code.strip().upper()
    if not code:
        return code

    if "." in code:
        base, exchange = code.split(".", 1)
        return f"{base}.{exchange}"

    if len(code) == 6 and code.isdigit():
        if code.startswith(("50", "51", "52", "53", "56", "58", "000")):
            return f"{code}.SH"
        if code.startswith(("15", "16", "18", "399")):
            return f"{code}.SZ"

    return code


class ETFWeight(BaseModel):
    stock_code: str = Field(..., description="ETF代码")
    weight: float = Field(..., ge=0, le=1, description="权重，0-1之间")

    @field_validator("stock_code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        code = normalize_stock_code(value)
        if not code:
            raise ValueError("ETF代码不能为空")
        return code


class BenchmarkWeight(BaseModel):
    stock_code: str = Field(..., description="基准指数代码")
    weight: float = Field(..., ge=0, le=1, description="基准权重，0-1之间")

    @field_validator("stock_code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        code = normalize_stock_code(value)
        if not code:
            raise ValueError("基准代码不能为空")
        return code


def default_benchmark_list() -> List[BenchmarkWeight]:
    return [
        BenchmarkWeight(stock_code="000001.SH", weight=0.5),
        BenchmarkWeight(stock_code="000300.SH", weight=0.5),
    ]


class BacktestRequest(BaseModel):
    etf_list: List[ETFWeight] = Field(..., description="ETF列表及权重")
    start_date: str = Field(..., description="回测开始日期 YYYY-MM-DD")
    end_date: str = Field(..., description="回测结束日期 YYYY-MM-DD")
    rebalance_freq: Literal["none", "month_start", "month_end", "week_start", "week_end"] = Field(
        ..., description="再均衡频率"
    )
    buy_fee_rate: float = Field(0.0003, ge=0, le=0.1, description="买入费率")
    sell_fee_rate: float = Field(0.0003, ge=0, le=0.1, description="卖出费率")
    benchmark_list: List[BenchmarkWeight] = Field(
        default_factory=default_benchmark_list,
        description="基准指数列表及权重",
    )

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_date(cls, value: str) -> str:
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("日期格式必须为 YYYY-MM-DD") from exc
        return value

    @model_validator(mode="after")
    def validate_period(self):
        if self.start_date > self.end_date:
            raise ValueError("开始日期不能晚于结束日期")
        if not self.etf_list:
            raise ValueError("至少需要选择一个ETF")
        if not self.benchmark_list:
            raise ValueError("至少需要选择一个基准指数")
        return self

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "etf_list": [
                    {"stock_code": "510300.SH", "weight": 0.075},
                    {"stock_code": "510500.SH", "weight": 0.075},
                    {"stock_code": "513500.SH", "weight": 0.075},
                    {"stock_code": "513100.SH", "weight": 0.075},
                    {"stock_code": "511010.SH", "weight": 0.15},
                    {"stock_code": "511260.SH", "weight": 0.40},
                    {"stock_code": "518880.SH", "weight": 0.075},
                    {"stock_code": "510170.SH", "weight": 0.075}
                ],
                "start_date": "2015-01-01",
                "end_date": "2026-07-04",
                "rebalance_freq": "month_start",
                "buy_fee_rate": 0.0003,
                "sell_fee_rate": 0.0003,
                "benchmark_list": [
                    {"stock_code": "000001.SH", "weight": 0.5},
                    {"stock_code": "000300.SH", "weight": 0.5}
                ]
            }
        }
    )


class BacktestResult(BaseModel):
    net_value_series: List[dict] = Field(..., description="净值曲线 [{date, net_value}]")
    benchmark_series: List[dict] = Field(default_factory=list, description="基准净值曲线 [{date, net_value}]")
    asset_return_series: dict = Field(default_factory=dict, description="ETF净值曲线 {stock_code: [{date, net_value}]}")
    metrics: dict = Field(..., description="回测指标")
    benchmark_metrics: dict = Field(default_factory=dict, description="基准指标")
    rebalance_records: List[dict] = Field(..., description="再均衡记录")
    warnings: List[str] = Field(default_factory=list, description="回测警告")


class ETFInfo(BaseModel):
    stock_code: str
    stock_name: str
    index_code: Optional[str] = None
    index_name: Optional[str] = None
    exchange: Optional[str] = None
    mgr_name: Optional[str] = None
    source: Optional[str] = None
