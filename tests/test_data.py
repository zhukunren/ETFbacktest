from __future__ import annotations

import pandas as pd
import pytest

from app import data


def test_catalog_uses_sina_when_eastmoney_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def unavailable() -> pd.DataFrame:
        raise ConnectionError("eastmoney unavailable")

    sina_catalog = pd.DataFrame(
        {
            "代码": ["sz159998", "sh510300"],
            "名称": ["计算机ETF天弘", "沪深300ETF"],
        }
    )
    monkeypatch.setattr(data.ak, "fund_etf_spot_em", unavailable)
    monkeypatch.setattr(
        data.ak,
        "fund_etf_category_sina",
        lambda symbol: sina_catalog,
    )

    catalog, source = data._download_catalog()

    assert source == "akshare-sina"
    assert catalog == [("159998", "计算机ETF天弘"), ("510300", "沪深300ETF")]


def test_catalog_reports_a_clear_error_when_all_akshare_sources_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(data.ak, "fund_etf_spot_em", lambda: (_ for _ in ()).throw(OSError()))
    monkeypatch.setattr(
        data.ak,
        "fund_etf_category_sina",
        lambda symbol: (_ for _ in ()).throw(OSError()),
    )

    with pytest.raises(data.MarketDataError, match="无法从 AkShare 拉取 ETF 列表"):
        data._download_catalog()


def test_history_uses_sina_when_eastmoney_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    seen_symbols: list[str] = []
    sina_history = pd.DataFrame(
        {
            "date": ["2024-01-02", "2024-01-03", "2024-01-04"],
            "close": [3.1, 3.2, 3.3],
        }
    )
    monkeypatch.setattr(
        data.ak,
        "fund_etf_hist_em",
        lambda **kwargs: (_ for _ in ()).throw(ConnectionError("eastmoney unavailable")),
    )

    def sina_loader(symbol: str) -> pd.DataFrame:
        seen_symbols.append(symbol)
        return sina_history

    monkeypatch.setattr(data.ak, "fund_etf_hist_sina", sina_loader)

    history = data._download_history("510300", pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-31"))

    assert seen_symbols == ["sh510300"]
    assert list(history["close"]) == [3.1, 3.2, 3.3]


def test_sina_symbol_prefers_the_expected_exchange() -> None:
    assert data._sina_symbols("510300") == ("sh510300", "sz510300")
    assert data._sina_symbols("159919") == ("sz159919", "sh159919")
