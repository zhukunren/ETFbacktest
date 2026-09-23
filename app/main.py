from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .backtest import build_price_frame, run_backtest
from .config import STATIC_DIR
from .data import MarketDataError, catalog_status, get_history, refresh_catalog, search_etfs
from .models import BacktestRequest


app = FastAPI(title="ETF Lab", version="0.1.0")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/catalog/status")
def get_catalog_status() -> dict[str, object]:
    return catalog_status()


@app.post("/api/catalog/refresh")
def refresh_etf_catalog() -> dict[str, object]:
    try:
        return refresh_catalog()
    except MarketDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/etfs/search")
def search_etf_catalog(
    q: str = Query(default="", max_length=40),
    limit: int = Query(default=12, ge=1, le=30),
) -> dict[str, object]:
    return {"items": search_etfs(q, limit)}


@app.post("/api/backtest")
def create_backtest(request: BacktestRequest) -> dict[str, object]:
    try:
        histories = {
            holding.code.strip(): get_history(
                holding.code.strip(), request.start_date.isoformat(), request.end_date.isoformat()
            )
            for holding in request.holdings
        }
        prices = build_price_frame(histories)
        result = run_backtest(request, prices)
    except (MarketDataError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    result["meta"] = {
        "start_date": prices.index[0].strftime("%Y-%m-%d"),
        "end_date": prices.index[-1].strftime("%Y-%m-%d"),
        "strategy": request.strategy,
        "price_basis": "AkShare ETF 日收盘价（东财优先，新浪备用）",
    }
    return result


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
