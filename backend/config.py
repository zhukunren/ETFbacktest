from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator
from pathlib import Path
from typing import Optional
import os
import sys

if sys.platform == "win32":
    import winreg


BACKEND_DIR = Path(__file__).resolve().parent


def get_windows_registry_env(name: str) -> Optional[str]:
    """Read User/Machine environment variables on Windows if not inherited."""
    if sys.platform != "win32":
        return None

    registry_locations = [
        (winreg.HKEY_CURRENT_USER, "Environment"),
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
        ),
    ]
    for root, path in registry_locations:
        try:
            with winreg.OpenKey(root, path) as key:
                value, _ = winreg.QueryValueEx(key, name)
                if value:
                    return str(value)
        except OSError:
            continue
    return None


def get_env_value(name: str) -> Optional[str]:
    return os.getenv(name) or get_windows_registry_env(name)


def is_placeholder_secret(value: Optional[str]) -> bool:
    token = (value or "").strip()
    if not token:
        return True
    placeholder_tokens = {"your_tushare_token", "你的tushare token"}
    return (
        token.lower() in placeholder_tokens
        or token.lower().startswith("your_")
        or token.startswith("你的")
    )


def first_real_value(*values: Optional[str]) -> str:
    for value in values:
        token = (value or "").strip()
        if token and not is_placeholder_secret(token):
            return token
    return ""


class Settings(BaseSettings):
    # Database
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = ""
    DB_NAME: str = "etf_data"
    ETF_DB_NAME: Optional[str] = None
    INDEX_DB_NAME: str = "stock_data"
    MYSQL_USER: Optional[str] = None
    MYSQL_PASSWORD: Optional[str] = None

    # Data provider
    TUSHARE_TOKEN: str = ""
    TUSHARETOKEN: Optional[str] = None
    TS_TOKEN: Optional[str] = None
    tushare_token: Optional[str] = None
    tusharetoken: Optional[str] = None

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        case_sensitive=True,
    )

    @model_validator(mode="after")
    def apply_mysql_env_aliases(self):
        """Prefer MYSQL_* env vars while keeping DB_* backward compatible."""
        mysql_user = self.MYSQL_USER or get_env_value("MYSQL_USER")
        mysql_password = self.MYSQL_PASSWORD or get_env_value("MYSQL_PASSWORD")
        tushare_token = first_real_value(
            self.TUSHARE_TOKEN,
            self.TUSHARETOKEN,
            self.TS_TOKEN,
            self.tushare_token,
            self.tusharetoken,
            get_env_value("TUSHARE_TOKEN"),
            get_env_value("TUSHARETOKEN"),
            get_env_value("TS_TOKEN"),
            get_env_value("tushare_token"),
            get_env_value("tusharetoken"),
        )

        if mysql_user is not None:
            self.DB_USER = mysql_user
        if mysql_password is not None:
            self.DB_PASSWORD = mysql_password
        self.TUSHARE_TOKEN = tushare_token
        if self.ETF_DB_NAME is None:
            self.ETF_DB_NAME = self.DB_NAME
        return self

    def validate_database_credentials(self):
        missing = []
        if not self.DB_USER:
            missing.append("MYSQL_USER")
        if not self.DB_PASSWORD:
            missing.append("MYSQL_PASSWORD")
        if missing:
            names = ", ".join(missing)
            raise ValueError(f"缺少数据库环境变量: {names}。请先设置后重启后端服务。")

    def effective_tushare_token(self) -> str:
        """Return a usable token, ignoring placeholder values from examples."""
        token = (self.TUSHARE_TOKEN or "").strip()
        if is_placeholder_secret(token):
            return ""
        return token

    def cors_origins(self) -> list[str]:
        origins = [
            origin.strip()
            for origin in (self.CORS_ORIGINS or "").split(",")
            if origin.strip()
        ]
        return origins or ["http://localhost:5173", "http://127.0.0.1:5173"]


settings = Settings()
