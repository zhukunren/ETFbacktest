import pymysql
from typing import Optional
import pandas as pd
from ..config import settings


class Database:
    def __init__(self):
        self.connection = None

    def connect(self):
        """建立数据库连接"""
        try:
            settings.validate_database_credentials()
            return pymysql.connect(
                host=settings.DB_HOST,
                port=settings.DB_PORT,
                user=settings.DB_USER,
                password=settings.DB_PASSWORD,
                database=settings.DB_NAME,
                charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor
            )
        except Exception as e:
            raise Exception(f"Database connection failed: {str(e)}")

    def close(self):
        """关闭数据库连接"""
        if self.connection:
            self.connection.close()

    def query_to_dataframe(self, sql: str, params: Optional[tuple] = None) -> pd.DataFrame:
        """执行查询并返回DataFrame"""
        try:
            connection = self.connect()
            try:
                with connection.cursor() as cursor:
                    cursor.execute(sql, params)
                    rows = cursor.fetchall()
                    columns = [column[0] for column in cursor.description] if cursor.description else []
            finally:
                connection.close()
            return pd.DataFrame(rows, columns=columns)
        except Exception as e:
            raise Exception(f"Query execution failed: {str(e)}")


# 全局数据库实例
db = Database()


def get_db():
    """获取数据库实例"""
    return db
