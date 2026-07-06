import pandas as pd
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple
from .database import get_db
from ..models.schemas import normalize_stock_code
from ..config import settings


DEFAULT_SECURITY_NAMES = {
    "510300.SH": "沪深300ETF",
    "510500.SH": "中证500ETF",
    "513500.SH": "标普500ETF",
    "513100.SH": "纳指ETF",
    "511010.SH": "5年国债ETF",
    "511260.SH": "10年国债ETF",
    "518880.SH": "黄金ETF",
    "510170.SH": "大宗商品ETF",
    "000001.SH": "上证指数",
}

PROJECT_DIR = Path(__file__).resolve().parents[2]
FALLBACK_ETF_LIST_PATH = PROJECT_DIR / "data" / "ETF列表.xlsx"


class MarketDataService:
    """市场数据服务"""

    def __init__(self):
        self.db = get_db()
        self._table_exists_cache: Dict[str, bool] = {}
        self._table_name_lookup_cache: Dict[str, Optional[str]] = {}
        self._columns_cache: Dict[str, set] = {}

    def get_etf_list(self) -> List[dict]:
        """获取当前上市ETF列表。Tushare失败时回退到本地Excel。"""
        records: Dict[str, dict] = {}
        tushare_error = None

        try:
            for record in self._get_etf_list_from_tushare():
                self._upsert_etf_record(records, **record)
        except ValueError as exc:
            tushare_error = str(exc)

        if not records:
            for record in self._get_etf_list_from_excel():
                self._upsert_etf_record(records, **record)

        if not records:
            detail = f"；Tushare错误: {tushare_error}" if tushare_error else ""
            raise ValueError(f"未能获取ETF列表，本地Excel也为空{detail}")

        return [records[code] for code in sorted(records, key=str.casefold)]

    def _get_etf_list_from_tushare(self) -> List[dict]:
        token = settings.effective_tushare_token()
        if not token:
            raise ValueError("未读取到TUSHARE_TOKEN。请设置环境变量 TUSHARE_TOKEN 或 TUSHARETOKEN 后重启后端。")

        try:
            import tushare as ts
        except ImportError:
            raise ValueError("未安装tushare依赖，请在backend目录执行 pip install -r requirements.txt。")

        try:
            ts.set_token(token)
            pro = ts.pro_api()
            df = pro.etf_basic(
                list_status="L",
                fields="ts_code,extname,index_code,index_name,exchange,mgr_name",
            )
        except Exception as exc:
            raise ValueError(f"Tushare ETF列表拉取失败: {exc}") from exc

        if df is None or df.empty:
            raise ValueError("Tushare ETF列表为空，请检查账号权限或稍后重试。")

        records = []
        for row in df.to_dict("records"):
            records.append({
                "stock_code": row.get("ts_code"),
                "stock_name": row.get("extname"),
                "index_code": row.get("index_code"),
                "index_name": row.get("index_name"),
                "exchange": row.get("exchange"),
                "mgr_name": row.get("mgr_name"),
                "source": "tushare",
            })
        return records

    def _get_etf_list_from_excel(self) -> List[dict]:
        if not FALLBACK_ETF_LIST_PATH.exists():
            raise ValueError(f"本地ETF列表文件不存在: {FALLBACK_ETF_LIST_PATH}")

        try:
            df = pd.read_excel(FALLBACK_ETF_LIST_PATH, sheet_name=0)
        except ImportError as exc:
            raise ValueError("读取ETF列表.xlsx需要openpyxl，请执行 pip install -r requirements.txt。") from exc
        except Exception as exc:
            raise ValueError(f"读取本地ETF列表失败: {exc}") from exc

        return self._records_from_excel_frame(df)

    def _records_from_excel_frame(self, df: pd.DataFrame) -> List[dict]:
        if df is None or df.empty:
            return []

        columns = {
            self._normalize_column_name(column): column
            for column in df.columns
        }

        def value(row, *names):
            for name in names:
                column = columns.get(self._normalize_column_name(name))
                if column is not None:
                    return row.get(column)
            return None

        records = []
        for row in df.to_dict("records"):
            records.append({
                "stock_code": value(row, "代码", "ts_code", "stock_code", "基金代码"),
                "stock_name": value(row, "名称", "extname", "stock_name", "基金简称", "基金名称"),
                "index_code": value(row, "跟踪指数代码", "index_code"),
                "index_name": value(row, "跟踪指数名称", "index_name", "指数名称"),
                "exchange": value(row, "上市地", "exchange", "交易所"),
                "mgr_name": value(row, "管理公司", "mgr_name", "基金管理人"),
                "source": "excel",
            })
        return records

    def _normalize_column_name(self, value: object) -> str:
        return re.sub(r"\s+", "", str(value or "").strip().lower())

    def _upsert_etf_record(
        self,
        records: Dict[str, dict],
        stock_code: object,
        stock_name: Optional[object] = None,
        prefer_existing: bool = False,
        **metadata,
    ):
        code = normalize_stock_code(str(stock_code or ""))
        if not code or not self._looks_like_etf(code):
            return

        existing = records.get(code)
        if existing and prefer_existing:
            return

        default_name = DEFAULT_SECURITY_NAMES.get(code, code)
        name = str(stock_name).strip() if stock_name is not None else ""
        if not name or name.lower() == "nan":
            name = default_name

        if not existing:
            existing = {"stock_code": code, "stock_name": name}
            records[code] = existing
        elif name and existing.get("stock_name") in (None, "", code, default_name):
            existing["stock_name"] = name

        for key, value in metadata.items():
            if value is None:
                continue
            text = str(value).strip()
            if text and text.lower() != "nan":
                existing[key] = text

    def get_price_data(
        self,
        stock_codes: List[str],
        start_date: str,
        end_date: str
    ) -> pd.DataFrame:
        """
        获取价格数据

        Args:
            stock_codes: 股票代码列表
            start_date: 开始日期 YYYY-MM-DD
            end_date: 结束日期 YYYY-MM-DD

        Returns:
            包含 trade_date, stock_code, close, adj_factor 的DataFrame
        """
        normalized_codes = [normalize_stock_code(code) for code in stock_codes]
        normalized_codes = [code for code in dict.fromkeys(normalized_codes) if code]
        if not normalized_codes:
            return pd.DataFrame()

        frames = [
            self._get_price_data_from_unified_table(normalized_codes, start_date, end_date),
            self._get_price_data_from_code_tables(normalized_codes, start_date, end_date),
        ]
        frames = [frame for frame in frames if not frame.empty]

        if not frames:
            return pd.DataFrame(columns=["trade_date", "stock_code", "adj_close"])

        df = pd.concat(frames, ignore_index=True)
        df = df.drop_duplicates(subset=["trade_date", "stock_code"], keep="first")
        df = df.sort_values(["trade_date", "stock_code"]).reset_index(drop=True)
        return df[["trade_date", "stock_code", "adj_close"]]

    def get_benchmark_data(
        self,
        benchmark_code: str,
        start_date: str,
        end_date: str
    ) -> pd.DataFrame:
        """获取基准价格数据。"""
        return self.get_price_data([benchmark_code], start_date, end_date)

    def get_trading_calendar(self, start_date: str, end_date: str) -> List[str]:
        """获取交易日历"""
        sql = f"""
        SELECT DISTINCT trade_date
        FROM {self._qualified_table(settings.DB_NAME, "stock_daily_price")}
        WHERE trade_date >= %s AND trade_date <= %s
        ORDER BY trade_date
        """
        df = self.db.query_to_dataframe(sql, (start_date, end_date))
        return df['trade_date'].tolist()

    def _get_price_data_from_unified_table(
        self,
        stock_codes: Sequence[str],
        start_date: str,
        end_date: str
    ) -> pd.DataFrame:
        if not self._table_exists("stock_daily_price", settings.DB_NAME):
            return pd.DataFrame()

        columns = self._columns_for_table("stock_daily_price", settings.DB_NAME)
        if "trade_date" not in columns or "stock_code" not in columns or "close" not in columns:
            return pd.DataFrame()

        query_codes = self._query_code_variants(stock_codes)
        placeholders = ",".join(["%s"] * len(query_codes))
        adj_expr = "adj_factor" if "adj_factor" in columns else "1 AS adj_factor"
        sql = f"""
        SELECT trade_date, stock_code, close, {adj_expr}
        FROM {self._qualified_table(settings.DB_NAME, "stock_daily_price")}
        WHERE stock_code IN ({placeholders})
          AND trade_date >= %s
          AND trade_date <= %s
        ORDER BY trade_date, stock_code
        """
        params = tuple(query_codes) + (start_date, end_date)
        df = self.db.query_to_dataframe(sql, params)
        if df.empty:
            return df

        requested_by_base = self._requested_by_base(stock_codes)
        df["stock_code"] = df["stock_code"].map(
            lambda code: self._map_row_code_to_requested(str(code), stock_codes, requested_by_base)
        )
        df = df[df["stock_code"].notna()]
        return self._normalize_price_frame(df)

    def _get_price_data_from_code_tables(
        self,
        stock_codes: Sequence[str],
        start_date: str,
        end_date: str
    ) -> pd.DataFrame:
        frames = []
        for code in stock_codes:
            code_table = self._find_code_table(code)
            if not code_table:
                continue
            schema_name, table_name = code_table

            columns = self._columns_for_table(table_name, schema_name)
            if "trade_date" not in columns or "close" not in columns:
                continue

            adj_expr = "adj_factor" if "adj_factor" in columns else "1 AS adj_factor"
            sql = f"""
            SELECT trade_date, %s AS stock_code, close, {adj_expr}
            FROM {self._qualified_table(schema_name, table_name)}
            WHERE trade_date >= %s
              AND trade_date <= %s
            ORDER BY trade_date
            """
            df = self.db.query_to_dataframe(sql, (code, start_date, end_date))
            if not df.empty:
                frames.append(self._normalize_price_frame(df))

        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)

    def _normalize_price_frame(self, df: pd.DataFrame) -> pd.DataFrame:
        normalized = df.copy()
        normalized["trade_date"] = pd.to_datetime(normalized["trade_date"]).dt.strftime("%Y-%m-%d")
        normalized["close"] = pd.to_numeric(normalized["close"], errors="coerce")
        normalized["adj_factor"] = pd.to_numeric(
            normalized.get("adj_factor", 1.0),
            errors="coerce"
        ).fillna(1.0)
        normalized["adj_close"] = normalized["close"] * normalized["adj_factor"]
        normalized = normalized.dropna(subset=["trade_date", "stock_code", "adj_close"])
        normalized["stock_code"] = normalized["stock_code"].map(normalize_stock_code)
        return normalized[["trade_date", "stock_code", "adj_close"]]

    def _query_code_variants(self, stock_codes: Sequence[str]) -> List[str]:
        variants = []
        for code in stock_codes:
            normalized = normalize_stock_code(code)
            base = normalized.split(".")[0]
            variants.extend([normalized, base, normalized.replace(".", "_")])
        return list(dict.fromkeys(variants))

    def _requested_by_base(self, stock_codes: Sequence[str]) -> Dict[str, str]:
        mapping = {}
        for code in stock_codes:
            normalized = normalize_stock_code(code)
            mapping.setdefault(normalized.split(".")[0], normalized)
        return mapping

    def _map_row_code_to_requested(
        self,
        raw_code: str,
        requested_codes: Sequence[str],
        requested_by_base: Dict[str, str]
    ) -> Optional[str]:
        normalized = normalize_stock_code(raw_code.replace("_", "."))
        if normalized in requested_codes:
            return normalized
        return requested_by_base.get(normalized.split(".")[0])

    def _table_exists(self, table_name: str, schema_name: str) -> bool:
        cache_key = f"{schema_name}.{table_name}"
        if cache_key in self._table_exists_cache:
            return self._table_exists_cache[cache_key]
        exists = self._find_table_name(table_name, schema_name) is not None
        self._table_exists_cache[cache_key] = exists
        return exists

    def _find_table_name(self, table_name: str, schema_name: str) -> Optional[str]:
        cache_key = f"{schema_name}.{table_name}"
        if cache_key in self._table_name_lookup_cache:
            return self._table_name_lookup_cache[cache_key]
        if not self._is_safe_table_name(table_name) or not self._is_safe_table_name(schema_name):
            self._table_name_lookup_cache[cache_key] = None
            return None

        sql = """
        SELECT table_name AS table_name
        FROM information_schema.tables
        WHERE table_schema = %s
          AND table_name = %s
        LIMIT 1
        """
        df = self.db.query_to_dataframe(sql, (schema_name, table_name))
        if df.empty:
            sql = """
            SELECT table_name AS table_name
            FROM information_schema.tables
            WHERE table_schema = %s
              AND LOWER(table_name) = LOWER(%s)
            ORDER BY table_name
            LIMIT 1
            """
            df = self.db.query_to_dataframe(sql, (schema_name, table_name))

        actual_name = None if df.empty else str(df.iloc[0]["table_name"])
        self._table_name_lookup_cache[cache_key] = actual_name
        return actual_name

    def _columns_for_table(self, table_name: str, schema_name: str) -> set:
        cache_key = f"{schema_name}.{table_name}"
        if cache_key in self._columns_cache:
            return self._columns_cache[cache_key]
        if not self._is_safe_table_name(table_name) or not self._is_safe_table_name(schema_name):
            self._columns_cache[cache_key] = set()
            return set()
        sql = """
        SELECT column_name AS column_name
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = %s
        """
        df = self.db.query_to_dataframe(sql, (schema_name, table_name))
        columns = {str(column).lower() for column in df["column_name"].tolist()}
        self._columns_cache[cache_key] = columns
        return columns

    def _list_code_tables(self, schema_name: str) -> List[str]:
        if not self._is_safe_table_name(schema_name):
            return []
        sql = """
        SELECT table_name AS table_name
        FROM information_schema.tables
        WHERE table_schema = %s
          AND table_name REGEXP '^[0-9]{6}_([sS][hH]|[sS][zZ])$'
        ORDER BY table_name
        """
        df = self.db.query_to_dataframe(sql, (schema_name,))
        return [str(name) for name in df["table_name"].tolist()]

    def _get_latest_name_from_code_table(self, table_name: str, code: str, schema_name: str) -> str:
        columns = self._columns_for_table(table_name, schema_name)
        name_column = None
        if "name" in columns:
            name_column = "name"
        elif "stock_name" in columns:
            name_column = "stock_name"
        if not name_column:
            return DEFAULT_SECURITY_NAMES.get(code, code)

        order_expr = "ORDER BY trade_date DESC" if "trade_date" in columns else ""
        sql = f"""
        SELECT `{name_column}` AS stock_name
        FROM {self._qualified_table(schema_name, table_name)}
        WHERE `{name_column}` IS NOT NULL
          AND `{name_column}` <> ''
        {order_expr}
        LIMIT 1
        """
        df = self.db.query_to_dataframe(sql)
        if df.empty:
            return DEFAULT_SECURITY_NAMES.get(code, code)
        return str(df.iloc[0]["stock_name"])

    def _table_name_for_code(self, stock_code: str) -> Optional[str]:
        normalized = normalize_stock_code(stock_code)
        if "." not in normalized:
            return None
        table_name = normalized.replace(".", "_")
        if not self._is_safe_table_name(table_name):
            return None
        return table_name

    def _table_names_for_code(self, stock_code: str) -> List[str]:
        table_name = self._table_name_for_code(stock_code)
        if not table_name:
            return []
        return list(dict.fromkeys([table_name, table_name.lower(), table_name.upper()]))

    def _find_code_table(self, stock_code: str) -> Optional[Tuple[str, str]]:
        for schema_name in self._candidate_schemas_for_code(stock_code):
            for table_name in self._table_names_for_code(stock_code):
                actual_table_name = self._find_table_name(table_name, schema_name)
                if actual_table_name:
                    return schema_name, actual_table_name
        return None

    def _candidate_etf_schemas(self) -> List[str]:
        candidates = [settings.ETF_DB_NAME, settings.DB_NAME, "etf_data"]
        return [schema for schema in dict.fromkeys(candidates) if schema]

    def _find_schema_for_code_table(self, stock_code: str, table_name: Optional[str]) -> Optional[str]:
        if table_name is None:
            return None
        for schema_name in self._candidate_schemas_for_code(stock_code):
            if self._find_table_name(table_name, schema_name):
                return schema_name
        return None

    def _candidate_schemas_for_code(self, stock_code: str) -> List[str]:
        base = normalize_stock_code(stock_code).split(".")[0]
        if base.startswith("000"):
            candidates = [settings.INDEX_DB_NAME, settings.DB_NAME, settings.ETF_DB_NAME, "stock_data"]
        else:
            candidates = [settings.ETF_DB_NAME, settings.DB_NAME, "etf_data"]
        return [schema for schema in dict.fromkeys(candidates) if schema]

    def _is_safe_table_name(self, table_name: str) -> bool:
        return bool(re.fullmatch(r"[A-Za-z0-9_]+", table_name))

    def _qualified_table(self, schema_name: str, table_name: str) -> str:
        if not self._is_safe_table_name(schema_name) or not self._is_safe_table_name(table_name):
            raise ValueError("Unsafe database or table name")
        return f"`{schema_name}`.`{table_name}`"

    def _code_from_table_name(self, table_name: str) -> Optional[str]:
        match = re.fullmatch(r"([0-9]{6})_([sS][hH]|[sS][zZ])", table_name)
        if not match:
            return None
        base, exchange = match.groups()
        return normalize_stock_code(f"{base}.{exchange.upper()}")

    def _looks_like_etf(self, stock_code: str) -> bool:
        base = stock_code.split(".")[0]
        return base.startswith(("50", "51", "56", "58", "15", "16", "18"))


market_data_service = MarketDataService()
