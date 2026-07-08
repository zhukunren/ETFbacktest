# -*- coding: utf-8 -*-
"""
Update ETF market data from TuShare into SQLite.

This script intentionally only handles ETF daily quotes:
- ETF universe: pro.etf_basic(list_status='L')
- Daily prices: ts.pro_bar(asset='FD', freq='D')
- Storage: SQLite tables etf_basic and etf_daily_price
"""

import argparse
import getpass
import io
import os
import re
import sqlite3
import sys
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import tushare as ts

warnings.filterwarnings("ignore", category=FutureWarning, module="tushare")

try:
    from tqdm import tqdm
except Exception:
    class _DummyTqdm:
        def __init__(self, *args, **kwargs):
            pass

        def update(self, n=1):
            pass

        def close(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            pass

    def tqdm(*args, **kwargs):  # noqa: N802
        return _DummyTqdm()


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = REPO_ROOT / "data" / "market_data.sqlite3"

TOKEN_ENV_NAMES = (
    "TUSHARE_TOKEN",
    "TUSHARETOKEN",
    "TS_TOKEN",
    "tushare_token",
    "tusharetoken",
)

ETF_BASIC_FIELDS = "ts_code,extname,index_code,index_name,exchange,mgr_name"
PRICE_COLUMNS = [
    "ts_code",
    "stock_code",
    "name",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "pre_close",
    "change",
    "pct_chg",
    "volume",
    "amount",
    "updated_at",
]


def log(message: str):
    text = str(message)
    try:
        tqdm.write(text)
    except Exception:
        print(text)


def parse_tokens(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [part.strip() for part in re.split(r"[,;\s]+", str(raw)) if part.strip()]


def get_windows_registry_env(name: str) -> str | None:
    if sys.platform != "win32":
        return None
    try:
        import winreg
    except Exception:
        return None

    locations = [
        (winreg.HKEY_CURRENT_USER, "Environment"),
        (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
    ]
    for root, path in locations:
        try:
            with winreg.OpenKey(root, path) as key:
                value, _ = winreg.QueryValueEx(key, name)
                if value:
                    return str(value)
        except OSError:
            continue
    return None


def get_env_value(name: str) -> str | None:
    return os.getenv(name) or get_windows_registry_env(name)


def is_placeholder_secret(value: str | None) -> bool:
    token = str(value or "").strip()
    if not token:
        return True
    lowered = token.lower()
    return lowered.startswith("your_") or token.startswith("你的") or lowered in {
        "your_tushare_token",
        "你的tushare token",
    }


def resolve_tushare_token(args: argparse.Namespace) -> str:
    values: list[str] = []
    if args.tushare_tokens:
        for item in args.tushare_tokens:
            values.extend(parse_tokens(item))
    elif args.tushare_token_env:
        values.extend(parse_tokens(get_env_value(args.tushare_token_env)))
    elif args.tushare_token_prompt:
        values.append(getpass.getpass("TuShare token: "))
    else:
        for env_name in TOKEN_ENV_NAMES:
            values.extend(parse_tokens(get_env_value(env_name)))

    for token in values:
        if not is_placeholder_secret(token):
            return token.strip()

    env_hint = ", ".join(TOKEN_ENV_NAMES)
    raise RuntimeError(f"缺少 TuShare token。请设置环境变量 {env_hint}，或使用 --tushare-token 传入。")


def normalize_code(value: str) -> str:
    code = str(value or "").strip().upper()
    if not code:
        return ""
    if "." in code:
        base, exchange = code.split(".", 1)
        return f"{base}.{exchange}"
    if len(code) == 6 and code.isdigit():
        if code.startswith(("50", "51", "52", "56", "58")):
            return f"{code}.SH"
        if code.startswith(("15", "16", "18")):
            return f"{code}.SZ"
    return code


def parse_yyyymmdd(value: str) -> str:
    text = str(value).strip()
    if not re.fullmatch(r"\d{8}", text):
        raise argparse.ArgumentTypeError("日期格式必须为 YYYYMMDD")
    datetime.strptime(text, "%Y%m%d")
    return text


def today_yyyymmdd() -> str:
    return datetime.now().strftime("%Y%m%d")


def connect_sqlite(db_path: Path) -> sqlite3.Connection:
    db_path = Path(db_path).expanduser()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=30000;")
    return conn


def ensure_schema(conn: sqlite3.Connection):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS etf_basic (
            ts_code TEXT PRIMARY KEY,
            stock_name TEXT,
            index_code TEXT,
            index_name TEXT,
            exchange TEXT,
            mgr_name TEXT,
            list_status TEXT,
            source TEXT,
            updated_at TEXT
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS etf_daily_price (
            ts_code TEXT NOT NULL,
            stock_code TEXT NOT NULL,
            name TEXT,
            trade_date TEXT NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            pre_close REAL,
            change REAL,
            pct_chg REAL,
            volume REAL,
            amount REAL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (ts_code, trade_date)
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_etf_daily_stock_date ON etf_daily_price(stock_code, trade_date);")
    conn.commit()


def call_with_retry(fn, label: str, retries: int, delay: float):
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return fn()
        except Exception as exc:
            last_error = exc
            if attempt >= retries:
                break
            wait = delay * attempt
            log(f"[{label}] 第 {attempt} 次失败：{exc}，{wait:.1f}s 后重试")
            time.sleep(wait)
    raise RuntimeError(f"{label} 重试 {retries} 次仍失败") from last_error


def fetch_etf_basic(pro, retries: int, retry_delay: float) -> pd.DataFrame:
    def _call():
        return pro.etf_basic(list_status="L", fields=ETF_BASIC_FIELDS)

    df = call_with_retry(_call, "etf_basic", retries, retry_delay)
    if df is None or df.empty:
        return pd.DataFrame(columns=["ts_code", "stock_name", "index_code", "index_name", "exchange", "mgr_name"])

    df = df.copy()
    df["ts_code"] = df["ts_code"].map(normalize_code)
    df["stock_name"] = df.get("extname", "")
    for col in ("index_code", "index_name", "exchange", "mgr_name"):
        if col not in df.columns:
            df[col] = None
    return df[["ts_code", "stock_name", "index_code", "index_name", "exchange", "mgr_name"]].dropna(subset=["ts_code"])


def upsert_etf_basic(conn: sqlite3.Connection, df: pd.DataFrame) -> int:
    if df is None or df.empty:
        return 0

    now = datetime.now().isoformat(timespec="seconds")
    rows = []
    for item in df.to_dict("records"):
        rows.append((
            item.get("ts_code"),
            item.get("stock_name"),
            item.get("index_code"),
            item.get("index_name"),
            item.get("exchange"),
            item.get("mgr_name"),
            "L",
            "tushare",
            now,
        ))

    conn.executemany(
        """
        INSERT INTO etf_basic (
            ts_code, stock_name, index_code, index_name, exchange, mgr_name, list_status, source, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(ts_code) DO UPDATE SET
            stock_name = COALESCE(excluded.stock_name, stock_name),
            index_code = COALESCE(excluded.index_code, index_code),
            index_name = COALESCE(excluded.index_name, index_name),
            exchange = COALESCE(excluded.exchange, exchange),
            mgr_name = COALESCE(excluded.mgr_name, mgr_name),
            list_status = excluded.list_status,
            source = excluded.source,
            updated_at = excluded.updated_at;
        """,
        rows,
    )
    conn.commit()
    return len(rows)


def latest_trade_date(conn: sqlite3.Connection, ts_code: str) -> str | None:
    row = conn.execute(
        "SELECT MAX(trade_date) FROM etf_daily_price WHERE ts_code = ?",
        (ts_code,),
    ).fetchone()
    if not row or not row[0]:
        return None
    return str(row[0])


def effective_start_date(conn: sqlite3.Connection, ts_code: str, requested_start: str, force_full: bool) -> str | None:
    if force_full:
        return requested_start

    latest = latest_trade_date(conn, ts_code)
    if not latest:
        return requested_start

    latest_dt = datetime.strptime(latest, "%Y-%m-%d")
    requested_dt = datetime.strptime(requested_start, "%Y%m%d")
    next_dt = latest_dt + timedelta(days=1)
    return max(requested_dt, next_dt).strftime("%Y%m%d")


def pro_bar(pro, ts_code: str, start_date: str, end_date: str, adj: str, retries: int, retry_delay: float) -> pd.DataFrame:
    kwargs = {
        "api": pro,
        "ts_code": ts_code,
        "start_date": start_date,
        "end_date": end_date,
        "asset": "FD",
        "freq": "D",
    }
    if adj:
        kwargs["adj"] = adj

    def _call():
        with redirect_stdout(io.StringIO()):
            return ts.pro_bar(**kwargs)

    df = call_with_retry(_call, f"{ts_code} pro_bar", retries, retry_delay)
    return pd.DataFrame() if df is None else df


def fetch_etf_daily(
    pro,
    ts_code: str,
    name: str | None,
    start_date: str,
    end_date: str,
    adj: str,
    retries: int,
    retry_delay: float,
) -> pd.DataFrame:
    if start_date > end_date:
        return pd.DataFrame()

    df = pro_bar(pro, ts_code, start_date, end_date, adj, retries, retry_delay)
    if df.empty:
        return df

    # TuShare may silently cap very long ranges. Split by year when the result touches the configured cap.
    max_rows = int(os.getenv("TS_MAX_ROWS", "5800"))
    if len(df) >= max_rows:
        frames = []
        start_dt = datetime.strptime(start_date, "%Y%m%d")
        end_dt = datetime.strptime(end_date, "%Y%m%d")
        year = start_dt.year
        while year <= end_dt.year:
            seg_start = max(start_dt, datetime(year, 1, 1)).strftime("%Y%m%d")
            seg_end = min(end_dt, datetime(year, 12, 31)).strftime("%Y%m%d")
            frames.append(pro_bar(pro, ts_code, seg_start, seg_end, adj, retries, retry_delay))
            year += 1
        df = pd.concat([frame for frame in frames if frame is not None and not frame.empty], ignore_index=True)

    return normalize_daily_df(df, ts_code, name)


def normalize_daily_df(df: pd.DataFrame, ts_code: str, name: str | None) -> pd.DataFrame:
    if df is None or df.empty or "trade_date" not in df.columns:
        return pd.DataFrame(columns=PRICE_COLUMNS)

    out = df.copy()
    if "vol" in out.columns and "volume" not in out.columns:
        out = out.rename(columns={"vol": "volume"})
    out["ts_code"] = normalize_code(ts_code)
    out["stock_code"] = out["ts_code"]
    out["name"] = name
    out["trade_date"] = pd.to_datetime(out["trade_date"], format="%Y%m%d", errors="coerce").dt.strftime("%Y-%m-%d")
    out = out.dropna(subset=["trade_date"])

    for col in ("open", "high", "low", "close", "pre_close", "change", "pct_chg", "volume", "amount"):
        if col not in out.columns:
            out[col] = None
        out[col] = pd.to_numeric(out[col], errors="coerce")

    out["updated_at"] = datetime.now().isoformat(timespec="seconds")
    out = out[PRICE_COLUMNS].sort_values("trade_date").drop_duplicates(subset=["ts_code", "trade_date"], keep="last")
    return out


def df_to_rows(df: pd.DataFrame) -> list[tuple]:
    clean = df[PRICE_COLUMNS].replace([float("inf"), float("-inf")], pd.NA)
    clean = clean.astype(object).where(pd.notna(clean), None)
    return [tuple(row) for row in clean.to_numpy()]


def upsert_daily(conn: sqlite3.Connection, df: pd.DataFrame) -> int:
    if df is None or df.empty:
        return 0
    rows = df_to_rows(df)
    conn.executemany(
        """
        INSERT INTO etf_daily_price (
            ts_code, stock_code, name, trade_date, open, high, low, close,
            pre_close, change, pct_chg, volume, amount, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(ts_code, trade_date) DO UPDATE SET
            stock_code = excluded.stock_code,
            name = COALESCE(excluded.name, name),
            open = COALESCE(excluded.open, open),
            high = COALESCE(excluded.high, high),
            low = COALESCE(excluded.low, low),
            close = COALESCE(excluded.close, close),
            pre_close = COALESCE(excluded.pre_close, pre_close),
            change = COALESCE(excluded.change, change),
            pct_chg = COALESCE(excluded.pct_chg, pct_chg),
            volume = COALESCE(excluded.volume, volume),
            amount = COALESCE(excluded.amount, amount),
            updated_at = excluded.updated_at;
        """,
        rows,
    )
    conn.commit()
    return len(rows)


def build_code_name_map(etf_basic: pd.DataFrame) -> dict[str, str]:
    if etf_basic is None or etf_basic.empty:
        return {}
    return {
        normalize_code(row["ts_code"]): str(row.get("stock_name") or "")
        for row in etf_basic.to_dict("records")
        if normalize_code(row.get("ts_code"))
    }


def update_etf_quotes(args: argparse.Namespace) -> int:
    token = resolve_tushare_token(args)
    ts.set_token(token)
    pro = ts.pro_api(token)

    db_path = Path(args.sqlite_db_path).expanduser()
    conn = connect_sqlite(db_path)
    ensure_schema(conn)

    etf_basic = fetch_etf_basic(pro, args.retries, args.retry_delay)
    basic_count = 0 if args.dry_run else upsert_etf_basic(conn, etf_basic)
    name_by_code = build_code_name_map(etf_basic)

    if args.codes:
        codes = [normalize_code(code) for code in args.codes if normalize_code(code)]
    else:
        codes = sorted(name_by_code)

    if not codes:
        raise RuntimeError("没有可更新的 ETF 代码。请检查 TuShare etf_basic 是否可用，或通过 --codes 指定。")

    tasks: list[tuple[str, str, str | None]] = []
    skipped = 0
    for code in codes:
        start = effective_start_date(conn, code, args.start_date, args.force_full)
        if start is None or start > args.end_date:
            skipped += 1
            continue
        tasks.append((code, start, name_by_code.get(code)))

    log(f"SQLite: {db_path}")
    log(f"ETF列表: {len(etf_basic)} 条，已写入 {basic_count} 条")
    log(f"行情任务: {len(tasks)} 只 ETF，跳过已最新 {skipped} 只")

    total_rows = 0
    failed: list[tuple[str, str]] = []
    workers = max(1, int(args.max_workers))

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {
            executor.submit(
                fetch_etf_daily,
                pro,
                code,
                name,
                start,
                args.end_date,
                args.adj,
                args.retries,
                args.retry_delay,
            ): (code, start)
            for code, start, name in tasks
        }

        with tqdm(total=len(future_map), desc="ETF行情更新", unit="只", dynamic_ncols=True) as bar:
            for future in as_completed(future_map):
                code, start = future_map[future]
                try:
                    df = future.result()
                    if args.dry_run:
                        rows = len(df)
                    else:
                        rows = upsert_daily(conn, df)
                    total_rows += rows
                    if rows == 0:
                        log(f"[{code}] {start}~{args.end_date} 无行情")
                except Exception as exc:
                    failed.append((code, str(exc)))
                    log(f"[{code}] 更新失败：{exc}")
                finally:
                    bar.update(1)

    conn.close()

    log(f"完成：写入/拉取行情 {total_rows} 行，失败 {len(failed)} 只")
    if failed:
        for code, error in failed[:20]:
            log(f"  - {code}: {error}")
        if len(failed) > 20:
            log(f"  ... 还有 {len(failed) - 20} 只失败")
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="只更新 ETF 日线行情到 SQLite")
    parser.add_argument("--start-date", type=parse_yyyymmdd, default="20000101", help="起始日期 YYYYMMDD，默认 20000101")
    parser.add_argument("--end-date", type=parse_yyyymmdd, default=today_yyyymmdd(), help="结束日期 YYYYMMDD，默认今天")
    parser.add_argument("--codes", nargs="*", help="仅更新指定 ETF 代码；不传则更新当前上市全部 ETF")
    parser.add_argument("--sqlite-db-path", default=str(DEFAULT_DB_PATH), help=f"SQLite 数据库文件，默认 {DEFAULT_DB_PATH}")
    parser.add_argument("--max-workers", type=int, default=int(os.getenv("ETF_UPDATE_MAX_WORKERS", "4")), help="并发拉取数量，默认 4")
    parser.add_argument("--force-full", action="store_true", help="忽略库内最新日期，按 start-date 全量覆盖更新")
    parser.add_argument("--dry-run", action="store_true", help="只拉取不写入 SQLite")
    parser.add_argument("--adj", default=os.getenv("PRO_BAR_ADJ", "").strip(), help="传给 ts.pro_bar 的复权参数，如 qfq/hfq；默认不复权")
    parser.add_argument("--retries", type=int, default=int(os.getenv("TS_RETRY_TIMES", "3")), help="TuShare 调用失败重试次数")
    parser.add_argument("--retry-delay", type=float, default=float(os.getenv("TS_RETRY_DELAY", "2.0")), help="重试退避基准秒数")
    parser.add_argument(
        "--tushare-token",
        "--ts-token",
        dest="tushare_tokens",
        action="append",
        help="TuShare token；也可设置 TUSHARE_TOKEN/TUSHARETOKEN/TS_TOKEN",
    )
    parser.add_argument("--tushare-token-env", help="从指定环境变量读取 TuShare token")
    parser.add_argument("--tushare-token-prompt", action="store_true", help="启动后交互输入 TuShare token")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return update_etf_quotes(args)


if __name__ == "__main__":
    raise SystemExit(main())
