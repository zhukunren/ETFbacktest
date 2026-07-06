import sys
from pathlib import Path
from contextlib import asynccontextmanager

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "backend"

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .api.routes import router
from .data.database import db
from .config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动API服务，数据库连接在首次查询时建立。"""
    print("API server started")
    try:
        yield
    finally:
        db.close()
        print("Database disconnected")


app = FastAPI(
    title="ETF再均衡回测系统",
    description="基于FastAPI的ETF再均衡回测API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(router, prefix="/api")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True
    )
