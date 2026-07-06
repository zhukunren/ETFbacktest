from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from typing import List
from ..models.schemas import BacktestRequest, BacktestResult, ETFInfo
from ..engine.rebalance_engine import rebalance_engine
from ..data.market_data import market_data_service
from ..config import settings

router = APIRouter()


@router.get("/etf/list", response_model=List[ETFInfo])
async def get_etf_list():
    """获取ETF列表"""
    try:
        etf_list = await run_in_threadpool(market_data_service.get_etf_list)
        return etf_list
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/backtest/run", response_model=BacktestResult)
async def run_backtest(request: BacktestRequest):
    """执行ETF再均衡回测"""
    try:
        # 验证权重总和
        total_weight = sum(item.weight for item in request.etf_list)
        if abs(total_weight - 1.0) > 0.0001:
            raise HTTPException(
                status_code=400,
                detail=f"权重总和必须为1，当前为 {total_weight:.4f}"
            )

        # 执行回测
        result = await run_in_threadpool(rebalance_engine.run_backtest, request)
        return result

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "ok"}


@router.get("/config/status")
async def config_status():
    """返回非敏感配置状态，便于排查环境变量。"""
    return {
        "db_host_set": bool(settings.DB_HOST),
        "db_port": settings.DB_PORT,
        "db_name_set": bool(settings.DB_NAME),
        "etf_db_name_set": bool(settings.ETF_DB_NAME),
        "index_db_name_set": bool(settings.INDEX_DB_NAME),
        "db_user_set": bool(settings.DB_USER),
        "mysql_password_set": bool(settings.DB_PASSWORD),
        "tushare_token_set": bool(settings.effective_tushare_token()),
        "cors_origins": settings.cors_origins(),
    }
