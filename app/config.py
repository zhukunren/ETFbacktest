from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
PRICE_CACHE_DIR = CACHE_DIR / "prices"
ETF_DB_PATH = DATA_DIR / "etf_catalog.sqlite3"
STATIC_DIR = Path(__file__).resolve().parent / "static"

for directory in (DATA_DIR, CACHE_DIR, PRICE_CACHE_DIR):
    directory.mkdir(parents=True, exist_ok=True)

