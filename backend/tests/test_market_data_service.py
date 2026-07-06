import unittest

import pandas as pd

from backend.data.market_data import MarketDataService


class MarketDataServiceTest(unittest.TestCase):
    def test_get_etf_list_uses_only_tushare_and_preserves_metadata(self):
        service = MarketDataService()
        service._get_etf_list_from_tushare = lambda: [
            {
                "stock_code": "588000.SH",
                "stock_name": "科创50ETF",
                "index_code": "000688.SH",
                "index_name": "科创50",
                "exchange": "SSE",
                "mgr_name": "测试基金",
                "source": "tushare",
            }
        ]
        service._table_exists = lambda table_name, schema_name: self.fail("ETF列表不应访问MySQL")
        service._list_code_tables = lambda schema_name: self.fail("ETF列表不应扫描分表")

        records = {
            record["stock_code"]: record
            for record in service.get_etf_list()
        }

        self.assertEqual(set(records), {"588000.SH"})
        self.assertEqual(records["588000.SH"]["index_name"], "科创50")
        self.assertEqual(records["588000.SH"]["source"], "tushare")

    def test_get_etf_list_falls_back_to_excel_when_tushare_fails(self):
        service = MarketDataService()
        service._get_etf_list_from_tushare = lambda: (_ for _ in ()).throw(ValueError("tushare down"))
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

    def test_get_etf_list_reports_empty_tushare_and_excel_result(self):
        service = MarketDataService()
        service._get_etf_list_from_tushare = lambda: []
        service._get_etf_list_from_excel = lambda: []

        with self.assertRaisesRegex(ValueError, "未能获取ETF列表"):
            service.get_etf_list()

    def test_code_table_helpers_keep_documented_uppercase_and_accept_lowercase(self):
        service = MarketDataService()

        self.assertEqual(service._table_name_for_code("510300.SH"), "510300_SH")
        self.assertEqual(service._code_from_table_name("159915_sz"), "159915.SZ")
        self.assertEqual(service._code_from_table_name("510300_SH"), "510300.SH")
        self.assertIsNone(service._code_from_table_name("not_an_etf"))


if __name__ == "__main__":
    unittest.main()
