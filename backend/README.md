# ETF再均衡回测系统 - 后端

基于FastAPI的ETF再均衡回测API服务。

## 功能特性

- ETF列表查询（优先读取SQLite，缺失时从AkShare获取，失败时读取 `data/ETF列表.xlsx`）
- 自定义权重配置
- 多种再均衡频率（不再平衡、月初/末、周初/末）
- 自定义回测周期
- 买入/卖出交易费率，默认各万分之三
- 自定义加权基准净值对比
- ETF无行情期间使用现金替代，并在回测结果中提示
- 完整的回测指标计算

## 技术栈

- FastAPI - Web框架
- pandas + numpy - 数据处理
- SQLite - 本地行情数据库
- pydantic - 数据验证

## 安装

```bash
cd backend
pip install -r requirements.txt
```

## 配置

复制 `.env.example` 为 `.env` 并配置SQLite数据库路径：

```ini
SQLITE_DB_PATH=data/market_data.sqlite3
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

后端实际读取状态可访问 `GET /api/config/status`，该接口只返回SQLite数据库路径、文件是否存在等非敏感配置状态。

## 运行

```bash
python app.py
```

服务将在 `http://localhost:8000` 启动。

API文档：`http://localhost:8000/docs`

## API接口

### 1. 获取ETF列表

```
GET /api/etf/list
```

### 2. 执行回测

```
POST /api/backtest/run
```

请求体示例：

```json
{
  "etf_list": [
    {"stock_code": "510300.SH", "weight": 0.075},
    {"stock_code": "510500.SH", "weight": 0.075},
    {"stock_code": "513500.SH", "weight": 0.075},
    {"stock_code": "513100.SH", "weight": 0.075},
    {"stock_code": "511010.SH", "weight": 0.15},
    {"stock_code": "511260.SH", "weight": 0.40},
    {"stock_code": "518880.SH", "weight": 0.075},
    {"stock_code": "510170.SH", "weight": 0.075}
  ],
  "start_date": "2015-01-01",
  "end_date": "2026-07-04",
  "rebalance_freq": "month_start",
  "buy_fee_rate": 0.0003,
  "sell_fee_rate": 0.0003,
  "benchmark_list": [
    {"stock_code": "000001.SH", "weight": 0.5},
    {"stock_code": "000300.SH", "weight": 0.5}
  ]
}
```

再均衡频率选项：
- `none` - 不再平衡，仅首个交易日建仓
- `month_start` - 月初
- `month_end` - 月末
- `week_start` - 周初
- `week_end` - 周末

### 数据库结构

SQLite数据库支持 `stock_daily_price` 单表、`tools/updata_data.py` 生成的 `etf_daily_price` 表，也支持 `510300_SH` 这类按代码分表。分表名大小写均可识别。`stock_daily_price` 至少包含 `stock_code`、`trade_date`、`close`；`etf_daily_price` 至少包含 `ts_code/stock_code`、`trade_date`、`close`；分表至少包含 `trade_date`、`close`。`stock_name/name` 和 `adj_factor` 可选。

### 定时数据更新

`tools/scheduled_update.py` 用于定时任务包装 `tools/updata_data.py`，提供进程锁、整轮失败重试和日志。systemd配置位于 `deploy/systemd/`，默认每天21:00运行，日志写入 `logs/data_update.log`。

## 项目结构

```
backend/
├── api/                  # API路由
│   └── routes.py
├── engine/              # 回测引擎
│   └── rebalance_engine.py
├── data/                # 数据层
│   ├── database.py
│   └── market_data.py
├── models/              # 数据模型
│   └── schemas.py
├── utils/               # 工具函数
│   └── date_utils.py
├── tests/               # 回归测试
├── app.py               # 应用入口
├── config.py            # 配置管理
└── requirements.txt     # 依赖包
```
