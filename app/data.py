from __future__ import annotations

import logging
import re
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Iterable

import akshare as ak
import pandas as pd

from .config import ETF_DB_PATH, PRICE_CACHE_DIR


CATALOG_TTL = timedelta(hours=24)
PRICE_COVERAGE_TOLERANCE = timedelta(days=10)
LOGGER = logging.getLogger(__name__)

# These are only used when the first network refresh is unavailable. A later refresh
# replaces the rows with the complete AkShare catalog.
FALLBACK_ETFS = [
    ("510050", "上证50ETF"),
    ("510300", "沪深300ETF"),
    ("510500", "中证500ETF"),
    ("512100", "中证1000ETF"),
    ("512480", "半导体ETF"),
    ("512760", "芯片ETF"),
    ("515030", "新能源ETF"),
    ("515050", "5GETF"),
    ("515790", "光伏ETF"),
    ("518880", "黄金ETF"),
    ("159915", "创业板ETF"),
    ("159919", "沪深300ETF"),
    ("159949", "创业板50ETF"),
    ("159967", "创成长ETF"),
    ("159928", "消费ETF"),
]


class MarketDataError(RuntimeError):
    """An AkShare data request could not be fulfilled."""


def _connection() -> sqlite3.Connection:
    conn = sqlite3.connect(ETF_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS etfs (
            code TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'unknown'
        )
        """
    )
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(etfs)").fetchall()}
    if "source" not in columns:
        conn.execute("ALTER TABLE etfs ADD COLUMN source TEXT NOT NULL DEFAULT 'unknown'")
    return conn


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _catalog_updated_at(conn: sqlite3.Connection) -> datetime | None:
    row = conn.execute("SELECT MAX(updated_at) AS updated_at FROM etfs").fetchone()
    if row is None or row["updated_at"] is None:
        return None
    return datetime.fromisoformat(row["updated_at"])


def _catalog_source(conn: sqlite3.Connection) -> str | None:
    row = conn.execute(
        "SELECT source FROM etfs ORDER BY updated_at DESC LIMIT 1"
    ).fetchone()
    return row["source"] if row and row["source"] else None


def _column_name(columns: Iterable[object], candidates: Iterable[str]) -> str | None:
    normalized = {str(column).strip().lower(): str(column) for column in columns}
    for candidate in candidates:
        if candidate.lower() in normalized:
            return normalized[candidate.lower()]
    for column in columns:
        text = str(column).strip().lower()
        if any(candidate.lower() in text for candidate in candidates):
            return str(column)
    return None


def _extract_catalog(raw: pd.DataFrame) -> list[tuple[str, str]]:
    if raw is None or raw.empty:
        raise ValueError("ETF 列表为空")

    code_column = _column_name(raw.columns, ["代码", "基金代码", "symbol", "code"])
    name_column = _column_name(raw.columns, ["名称", "基金简称", "name"])
    if not code_column or not name_column:
        raise ValueError("无法识别 ETF 列表中的代码或名称列")

    catalog: dict[str, str] = {}
    for code_value, name_value in zip(raw[code_column], raw[name_column], strict=False):
        code_text = str(code_value).strip()
        if re.fullmatch(r"\d+\.0", code_text):
            code_text = code_text[:-2]
        code = re.sub(r"\D", "", code_text).zfill(6)
        name = str(name_value).strip()
        if len(code) == 6 and name and name.lower() != "nan":
            catalog[code] = name
    if not catalog:
        raise ValueError("ETF 列表未包含可用代码")
    return sorted(catalog.items())


def _download_catalog() -> tuple[list[tuple[str, str]], str]:
    """Download an ETF catalog through AkShare with independent upstream fallbacks."""
    sources = [
        ("akshare-eastmoney", ak.fund_etf_spot_em, {}),
        ("akshare-sina", ak.fund_etf_category_sina, {"symbol": "ETF基金"}),
    ]
    failures: list[Exception] = []
    for source, loader, kwargs in sources:
        try:
            catalog = _extract_catalog(loader(**kwargs))
            LOGGER.info("Loaded %d ETFs through %s", len(catalog), source)
            return catalog, source
        except Exception as exc:  # AkShare relays several independent upstreams.
            failures.append(exc)
            LOGGER.warning("AkShare ETF catalog request failed for %s", source, exc_info=exc)

    raise MarketDataError("无法从 AkShare 拉取 ETF 列表，请检查网络或稍后重试") from failures[-1]


def refresh_catalog() -> dict[str, object]:
    catalog, source = _download_catalog()
    timestamp = _utc_now().isoformat()
    with _connection() as conn:
        conn.execute("DELETE FROM etfs")
        conn.executemany(
            "INSERT INTO etfs (code, name, updated_at, source) VALUES (?, ?, ?, ?)",
            [(code, name, timestamp, source) for code, name in catalog],
        )
    return {"count": len(catalog), "updated_at": timestamp, "source": source}


def _seed_catalog_if_empty() -> None:
    with _connection() as conn:
        count = conn.execute("SELECT COUNT(*) FROM etfs").fetchone()[0]
        if count:
            return
        timestamp = _utc_now().isoformat()
        conn.executemany(
            "INSERT INTO etfs (code, name, updated_at, source) VALUES (?, ?, ?, ?)",
            [(code, name, timestamp, "local-fallback") for code, name in FALLBACK_ETFS],
        )


def ensure_catalog() -> dict[str, object]:
    with _connection() as conn:
        updated_at = _catalog_updated_at(conn)
        count = conn.execute("SELECT COUNT(*) FROM etfs").fetchone()[0]

    stale = updated_at is None or _utc_now() - updated_at > CATALOG_TTL
    if count == 0 or stale:
        try:
            return refresh_catalog()
        except MarketDataError as exc:
            _seed_catalog_if_empty()
            with _connection() as conn:
                count = conn.execute("SELECT COUNT(*) FROM etfs").fetchone()[0]
                updated_at = _catalog_updated_at(conn)
                source = _catalog_source(conn)
            return {
                "count": count,
                "updated_at": updated_at.isoformat() if updated_at else None,
                "source": source or "unavailable",
                "warning": str(exc),
            }
    with _connection() as conn:
        source = _catalog_source(conn)
    return {
        "count": count,
        "updated_at": updated_at.isoformat(),
        "source": source or "local-cache",
    }


def catalog_status() -> dict[str, object]:
    return ensure_catalog()


def search_etfs(query: str, limit: int = 12) -> list[dict[str, str]]:
    ensure_catalog()
    normalized = query.strip().lower()
    with _connection() as conn:
        if normalized:
            rows = conn.execute(
                """
                SELECT code, name FROM etfs
                WHERE code LIKE ? OR lower(name) LIKE ?
                LIMIT 100
                """,
                (f"%{normalized}%", f"%{normalized}%"),
            ).fetchall()
        else:
            placeholders = ",".join("?" for _ in FALLBACK_ETFS)
            popular_codes = [code for code, _ in FALLBACK_ETFS]
            rows = conn.execute(
                f"SELECT code, name FROM etfs WHERE code IN ({placeholders})", popular_codes
            ).fetchall()

    def rank(row: sqlite3.Row) -> tuple[int, str]:
        code, name = row["code"], row["name"].lower()
        if not normalized:
            return (0, code)
        if code == normalized or name == normalized:
            return (0, code)
        if code.startswith(normalized) or name.startswith(normalized):
            return (1, code)
        return (2, code)

    return [
        {"code": row["code"], "name": row["name"]}
        for row in sorted(rows, key=rank)[:limit]
    ]


def _price_cache_path(code: str) -> Path:
    return PRICE_CACHE_DIR / f"{code}.csv"


def _read_price_cache(code: str) -> pd.DataFrame:
    path = _price_cache_path(code)
    if not path.exists():
        return pd.DataFrame(columns=["date", "close"])
    try:
        cached = pd.read_csv(path, dtype={"date": "string"})
        cached["date"] = pd.to_datetime(cached["date"], errors="coerce")
        cached["close"] = pd.to_numeric(cached["close"], errors="coerce")
        return cached.dropna(subset=["date", "close"])
    except (OSError, pd.errors.ParserError, ValueError):
        return pd.DataFrame(columns=["date", "close"])


def _write_price_cache(code: str, prices: pd.DataFrame) -> None:
    path = _price_cache_path(code)
    normalized = prices[["date", "close"]].copy()
    normalized["date"] = pd.to_datetime(normalized["date"]).dt.strftime("%Y-%m-%d")
    normalized.to_csv(path, index=False)


def _normalize_history(raw: pd.DataFrame, code: str) -> pd.DataFrame:
    if raw is None or raw.empty:
        raise ValueError(f"未找到 {code} 的行情")
    date_column = _column_name(raw.columns, ["日期", "date"])
    close_column = _column_name(raw.columns, ["收盘", "close", "收盘价"])
    if not date_column or not close_column:
        raise ValueError(f"无法识别 {code} 行情中的日期或收盘价列")

    result = pd.DataFrame(
        {
            "date": pd.to_datetime(raw[date_column], errors="coerce"),
            "close": pd.to_numeric(raw[close_column], errors="coerce"),
        }
    ).dropna(subset=["date", "close"])
    result = result[result["close"] > 0].drop_duplicates("date").sort_values("date")
    if result.empty:
        raise ValueError(f"{code} 行情不包含有效收盘价")
    return result


def _download_history_eastmoney(code: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    request = {
        "symbol": code,
        "period": "daily",
        "start_date": start.strftime("%Y%m%d"),
        "end_date": end.strftime("%Y%m%d"),
        "adjust": "qfq",
    }
    try:
        raw = ak.fund_etf_hist_em(**request)
    except TypeError:
        request.pop("adjust")
        raw = ak.fund_etf_hist_em(**request)
    return _normalize_history(raw, code)


def _sina_symbols(code: str) -> tuple[str, str]:
    """Return a likely exchange prefix first, then the alternate market."""
    preferred = "sh" if code.startswith(("5", "6")) else "sz"
    alternate = "sz" if preferred == "sh" else "sh"
    return f"{preferred}{code}", f"{alternate}{code}"


def _download_history_sina(code: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    errors: list[Exception] = []
    for symbol in _sina_symbols(code):
        try:
            result = _normalize_history(ak.fund_etf_hist_sina(symbol=symbol), code)
            result = result[(result["date"] >= start) & (result["date"] <= end)]
            if not result.empty:
                return result.reset_index(drop=True)
            errors.append(ValueError(f"{symbol} 在所选日期内没有行情"))
        except Exception as exc:
            errors.append(exc)
            LOGGER.warning("AkShare Sina ETF history request failed for %s", symbol, exc_info=exc)

    raise ValueError(f"新浪行情源未找到 {code} 在所选日期内的有效数据") from errors[-1]


def _download_history(code: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Prefer Eastmoney qfq bars and fall back to Sina daily close bars."""
    try:
        return _download_history_eastmoney(code, start, end)
    except Exception as eastmoney_error:
        LOGGER.warning("AkShare Eastmoney ETF history request failed for %s", code, exc_info=eastmoney_error)

    try:
        return _download_history_sina(code, start, end)
    except Exception as sina_error:
        LOGGER.warning("AkShare Sina ETF history fallback failed for %s", code, exc_info=sina_error)
        raise MarketDataError(f"{code} 行情下载失败，请检查网络或稍后重试") from sina_error


def get_history(code: str, start_date: str, end_date: str) -> pd.DataFrame:
    code = re.sub(r"\D", "", code).zfill(6)
    start = pd.Timestamp(start_date).normalize()
    end = pd.Timestamp(end_date).normalize()
    if start > end:
        raise MarketDataError("行情开始日期晚于结束日期")

    cached = _read_price_cache(code)
    # ETF bars exist only on trading days. A cache beginning after a calendar
    # holiday or ending before a weekend should still satisfy the request.
    has_coverage = (
        not cached.empty
        and cached["date"].min() <= start + PRICE_COVERAGE_TOLERANCE
        and cached["date"].max() >= end - PRICE_COVERAGE_TOLERANCE
    )
    if not has_coverage:
        downloaded = _download_history(code, start, end)
        combined = pd.concat([cached, downloaded], ignore_index=True)
        cached = combined.drop_duplicates("date", keep="last").sort_values("date")
        _write_price_cache(code, cached)

    result = cached[(cached["date"] >= start) & (cached["date"] <= end)].copy()
    if result.empty:
        raise MarketDataError(f"{code} 缓存中没有所选日期的行情")
    return result.reset_index(drop=True)
