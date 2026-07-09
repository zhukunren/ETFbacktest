import unittest
import sqlite3
import tempfile
from pathlib import Path

import pandas as pd

from backend.config import settings
from backend.data.market_data import MarketDataService
from backend.models.schemas import normalize_stock_code


class MarketDataServiceTest(unittest.TestCase):
    def test_normalize_stock_code_handles_common_index_codes(self):
        self.assertEqual(normalize_stock_code("000300"), "000300.SH")
        self.assertEqual(normalize_stock_code("399006"), "399006.SZ")

    def test_get_etf_list_prefers_sqlite_and_preserves_metadata(self):
        service = MarketDataService()
        service._get_etf_list_from_sqlite = lambda: [
            {
                "stock_code": "588000.SH",
                "stock_name": "科创50ETF",
                "index_code": "000688.SH",
                "index_name": "科创50",
                "exchange": "SSE",
                "mgr_name": "测试基金",
                "source": "akshare",
            }
        ]
        service._get_etf_list_from_akshare = lambda: self.fail("SQLite有ETF列表时不应访问AkShare")
        service._get_etf_list_from_excel = lambda: self.fail("SQLite有ETF列表时不应读取Excel")

        records = {
            record["stock_code"]: record
            for record in service.get_etf_list()
        }

        self.assertEqual(set(records), {"588000.SH"})
        self.assertEqual(records["588000.SH"]["index_name"], "科创50")
        self.assertEqual(records["588000.SH"]["source"], "akshare")

    def test_get_etf_list_falls_back_to_excel_when_akshare_fails(self):
        service = MarketDataService()
        service._get_etf_list_from_sqlite = lambda: []
        service._get_etf_list_from_akshare = lambda: (_ for _ in ()).throw(ValueError("akshare down"))
        service._get_etf_list_from_excel = lambda: [
            {
                "stock_code": "159792.SZ",
                "stock_name": "港股通互联网ETF富国",
                "index_name": "港股通互联网",
                "mgr_name": "富国基金",
                "exchange": "深圳证券交易所",
                "source": "excel",
            }
        ]

        records = service.get_etf_list()

        self.assertEqual(records[0]["stock_code"], "159792.SZ")
        self.assertEqual(records[0]["source"], "excel")

    def test_get_etf_list_reads_sqlite_etf_basic(self):
        original_db_path = settings.SQLITE_DB_PATH

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "market.sqlite3"
            connection = sqlite3.connect(db_path)
            try:
                connection.executescript(
                    """
                    CREATE TABLE etf_basic (
                        ts_code TEXT PRIMARY KEY,
                        stock_name TEXT,
                        index_name TEXT,
                        exchange TEXT,
                        mgr_name TEXT,
                        list_status TEXT,
                        source TEXT
                    );
                    INSERT INTO etf_basic VALUES (
                        '588000.SH', '科创50ETF', '科创50', '上海证券交易所', '测试基金', 'L', 'akshare'
                    );
                    """
                )
                connection.commit()
            finally:
                connection.close()

            settings.SQLITE_DB_PATH = str(db_path)
            try:
                service = MarketDataService()
                records = service.get_etf_list()
            finally:
                settings.SQLITE_DB_PATH = original_db_path

        self.assertEqual(records[0]["stock_code"], "588000.SH")
        self.assertEqual(records[0]["stock_name"], "科创50ETF")
        self.assertEqual(records[0]["source"], "akshare")

    def test_get_etf_list_keeps_new_sse_etf_prefixes_and_price_only_codes(self):
        original_db_path = settings.SQLITE_DB_PATH

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "market.sqlite3"
            connection = sqlite3.connect(db_path)
            try:
                connection.executescript(
                    """
                    CREATE TABLE etf_basic (
                        ts_code TEXT PRIMARY KEY,
                        stock_name TEXT,
                        index_name TEXT,
                        exchange TEXT,
                        mgr_name TEXT,
                        list_status TEXT,
                        source TEXT
                    );
                    INSERT INTO etf_basic VALUES
                        ('520500.SH', '恒生创新药ETF华泰柏瑞', NULL, '上海证券交易所', NULL, 'L', 'akshare'),
                        ('530000', '上证50ETF天弘', NULL, '上海证券交易所', NULL, 'L', 'akshare');

                    CREATE TABLE etf_daily_price (
                        ts_code TEXT,
                        stock_code TEXT,
                        name TEXT,
                        trade_date TEXT,
                        close REAL
                    );
                    INSERT INTO etf_daily_price VALUES
                        ('511260.SH', '511260.SH', NULL, '2024-01-02', 10.0);
                    """
                )
                connection.commit()
            finally:
                connection.close()

            settings.SQLITE_DB_PATH = str(db_path)
            try:
                service = MarketDataService()
                records = {
                    record["stock_code"]: record
                    for record in service.get_etf_list()
                }
            finally:
                settings.SQLITE_DB_PATH = original_db_path

        self.assertIn("520500.SH", records)
        self.assertIn("530000.SH", records)
        self.assertIn("511260.SH", records)
        self.assertEqual(records["511260.SH"]["stock_name"], "10年国债ETF")
        self.assertEqual(records["511260.SH"]["source"], "sqlite")

    def test_excel_records_map_chinese_columns(self):
        service = MarketDataService()
        df = pd.DataFrame([
            {
                "代码": "159792.SZ",
                "名称": "港股通互联网ETF富国",
                "管理公司": "富国基金",
                "跟踪指数名称": "港股通互联网",
                "上市地": "深圳证券交易所",
            }
        ])

        records = {
            record["stock_code"]: record
            for record in service._records_from_excel_frame(df)
        }

        self.assertEqual(records["159792.SZ"]["stock_name"], "港股通互联网ETF富国")
        self.assertEqual(records["159792.SZ"]["index_name"], "港股通互联网")
        self.assertEqual(records["159792.SZ"]["mgr_name"], "富国基金")
        self.assertEqual(records["159792.SZ"]["exchange"], "深圳证券交易所")

    def test_get_etf_list_reports_empty_all_sources_result(self):
        service = MarketDataService()
        service._get_etf_list_from_sqlite = lambda: []
        service._get_etf_list_from_akshare = lambda: []
        service._get_etf_list_from_excel = lambda: []

        with self.assertRaisesRegex(ValueError, "未能获取ETF列表"):
            service.get_etf_list()

    def test_code_table_helpers_keep_documented_uppercase_and_accept_lowercase(self):
        service = MarketDataService()

        self.assertEqual(service._table_name_for_code("510300.SH"), "510300_SH")
        self.assertEqual(service._code_from_table_name("159915_sz"), "159915.SZ")
        self.assertEqual(service._code_from_table_name("510300_SH"), "510300.SH")
        self.assertIsNone(service._code_from_table_name("not_an_etf"))
        self.assertEqual(normalize_stock_code("520500"), "520500.SH")
        self.assertEqual(normalize_stock_code("530000"), "530000.SH")
        self.assertTrue(service._looks_like_etf("520500.SH"))
        self.assertTrue(service._looks_like_etf("530000.SH"))

    def test_get_price_data_reads_sqlite_unified_and_code_tables(self):
        original_db_path = settings.SQLITE_DB_PATH

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "market.sqlite3"
            connection = sqlite3.connect(db_path)
            try:
                connection.executescript(
                    """
                    CREATE TABLE stock_daily_price (
                        stock_code TEXT,
                        trade_date TEXT,
                        close REAL,
                        adj_factor REAL
                    );
                    INSERT INTO stock_daily_price VALUES
                        ('510300.SH', '2024-01-02', 10.0, 1.1),
                        ('510300', '2024-01-03', 11.0, 1.0);

                    CREATE TABLE etf_daily_price (
                        ts_code TEXT,
                        stock_code TEXT,
                        name TEXT,
                        trade_date TEXT,
                        close REAL
                    );
                    INSERT INTO etf_daily_price VALUES
                        ('513500.SH', '513500.SH', '标普500ETF', '2024-01-02', 30.0),
                        ('513500.SH', '513500.SH', '标普500ETF', '2024-01-03', 31.0);

                    CREATE TABLE "510500_SH" (
                        trade_date TEXT,
                        close REAL
                    );
                    INSERT INTO "510500_SH" VALUES
                        ('2024-01-02', 20.0),
                        ('2024-01-03', 21.0);
                    """
                )
                connection.commit()
            finally:
                connection.close()

            settings.SQLITE_DB_PATH = str(db_path)
            try:
                service = MarketDataService()
                df = service.get_price_data(
                    ["510300.SH", "510500.SH", "513500.SH"],
                    "2024-01-01",
                    "2024-01-04",
                )
            finally:
                settings.SQLITE_DB_PATH = original_db_path

        records = {
            (row["trade_date"], row["stock_code"]): row["adj_close"]
            for row in df.to_dict("records")
        }

        self.assertAlmostEqual(records[("2024-01-02", "510300.SH")], 11.0)
        self.assertAlmostEqual(records[("2024-01-03", "510300.SH")], 11.0)
        self.assertAlmostEqual(records[("2024-01-02", "510500.SH")], 20.0)
        self.assertAlmostEqual(records[("2024-01-03", "510500.SH")], 21.0)
        self.assertAlmostEqual(records[("2024-01-02", "513500.SH")], 30.0)
        self.assertAlmostEqual(records[("2024-01-03", "513500.SH")], 31.0)


if __name__ == "__main__":
    unittest.main()
