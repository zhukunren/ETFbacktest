# ETF再均衡回测系统 - 快速启动指南

## 1. 后端启动

```powershell
# 进入后端目录
cd D:\项目\ETF再均衡回测系统\backend

# 配置SQLite数据库路径（复制 .env.example 为 .env）
Copy-Item .env.example .env

# 编辑 .env 文件，确认SQLite数据库文件路径
# SQLITE_DB_PATH=data/market_data.sqlite3
# CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

# 安装依赖
pip install -r requirements.txt

# 启动后端服务
python app.py
```

后端运行在：http://localhost:8000
API文档：http://localhost:8000/docs

## 2. 前端启动

```powershell
# 新开一个终端，进入前端目录
cd D:\项目\ETF再均衡回测系统\frontend

# 启动前端开发服务器
npm run dev
```

前端运行在：http://localhost:5173

## 3. 开始使用

1. 浏览器打开 http://localhost:5173
2. 默认组合已载入，也可以点击"添加ETF"调整ETF
3. 设置每个ETF的权重，运行回测时权重总和必须为1
4. 配置回测参数（日期、再均衡频率、交易费率、基准组合权重）
5. 点击"运行回测"查看结果

## 注意事项

- 可执行 `python tools/updata_data.py --start-date 20150101` 用AkShare更新SQLite行情库
- 已提供 `deploy/systemd/etf-data-update.timer`，可配置每天21:00自动更新行情
- SQLite数据库支持 `etf_daily_price`、`stock_daily_price` 单表或 `510300_SH` 这类按代码分表；SQLite只用于回测行情
- ETF选择列表优先读取SQLite，缺失时从AkShare拉取，失败时读取 `data\ETF列表.xlsx`
- 如果页面提示数据库连接失败，先打开前端同源地址 `/api/config/status`，例如 http://127.0.0.1:5173/api/config/status，检查前端代理和后端SQLite状态
- ETF无行情期间会自动保留对应目标权重为现金，并在回测结果中提示
- 默认买入/卖出费率均为0.0003
- 权重总和必须为1；系统不会自动改动已输入权重，点击"归一化"才会主动调整
- 首次运行可能需要等待数据加载

## 目录结构

```
ETF再均衡回测系统/
├── backend/           # Python后端（FastAPI）
├── frontend/          # Vue3前端
└── README.md          # 详细文档
```
