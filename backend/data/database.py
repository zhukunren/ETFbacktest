import sqlite3
from typing import Optional, Sequence
import pandas as pd
from ..config import settings


class Database:
    def __init__(self):
        self.connection = None

    def connect(self):
        """建立数据库连接"""
        try:
            db_path = settings.sqlite_db_path()
            db_path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(db_path)
            connection.row_factory = sqlite3.Row
            return connection
        except Exception as e:
            raise Exception(f"Database connection failed: {str(e)}")

    def close(self):
        """关闭数据库连接"""
        if self.connection:
            self.connection.close()

    def query_to_dataframe(self, sql: str, params: Optional[Sequence] = None) -> pd.DataFrame:
        """执行查询并返回DataFrame"""
        try:
            connection = self.connect()
            try:
                cursor = connection.cursor()
                cursor.execute(sql, tuple(params or ()))
                rows = cursor.fetchall()
                columns = [column[0] for column in cursor.description] if cursor.description else []
            finally:
                connection.close()
            return pd.DataFrame([dict(row) for row in rows], columns=columns)
        except Exception as e:
            raise Exception(f"Query execution failed: {str(e)}")


# 全局数据库实例
db = Database()


def get_db():
    """获取数据库实例"""
    return db
