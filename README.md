# ETF再均衡回测系统

一个基于 **Vue 3 + FastAPI** 的ETF再均衡回测系统。

## 功能特性

- 🎯 自定义ETF选择和权重配置，ETF列表优先读取SQLite，缺失时从AkShare获取，失败时读取本地Excel
- 📅 灵活的回测周期选择
- 🔄 多种再均衡频率（不再平衡、月初/末、周初/末）
- 📊 完整的回测指标、净值曲线和自定义加权基准对比
- 💡 清晰的再均衡记录追踪
- 💸 支持买入/卖出交易费率，默认各万分之三
- 💵 ETF无行情期间自动保留对应目标权重为现金，并在回测结果中提示

## 技术栈

### 后端
- FastAPI - 现代Python Web框架
- pandas + numpy - 数据处理和回测计算
- SQLite - 本地行情数据库
- pydantic - 数据验证

### 前端
- Vue 3 + Vite - 现代前端框架
- Element Plus - UI组件库
- ECharts - 数据可视化
- Axios - HTTP客户端

## 快速开始

### 1. 后端启动

```bash
cd backend

# 安装依赖
pip install -r requirements.txt

# 配置数据库路径（复制 .env.example 为 .env 并修改）
cp .env.example .env

# 启动服务
python app.py
```

后端服务运行在 `http://localhost:8000`

API文档：`http://localhost:8000/docs`

### 2. 前端启动

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

前端运行在 `http://localhost:5173`

## 项目结构

```
ETF再均衡回测系统/
├── backend/              # Python后端
│   ├── api/             # API路由
│   ├── engine/          # 回测引擎
│   ├── data/            # 数据层
│   ├── models/          # 数据模型
│   ├── utils/           # 工具函数
│   └── app.py           # 入口
├── frontend/            # Vue前端
│   ├── src/
│   │   ├── api/        # API调用
│   │   ├── App.vue     # 主组件
│   │   └── main.js     # 入口
│   └── package.json
└── README.md
```

## 使用说明

1. **选择ETF**：系统默认载入2015年以来的ETF再均衡组合，也可以点击"添加ETF"调整
2. **配置权重**：为每个ETF设置权重（权重总和必须为1）
3. **设置参数**：选择回测周期、再均衡频率、交易费率和基准组合权重
4. **运行回测**：点击"运行回测"查看结果

## 回测指标

- 总收益率
- 年化收益率
- 最大回撤
- 波动率（年化）
- 夏普比率
- 期末净值
- 再均衡次数

## 数据库要求

系统使用SQLite数据库保存回测行情，默认数据库文件为 `data/market_data.sqlite3`，支持多种行情结构。ETF选择列表优先读取SQLite中的 `etf_basic`，缺失时从AkShare获取，无法拉取时读取 `data/ETF列表.xlsx`。

### 单表结构

```sql
-- stock_daily_price 表
stock_code    VARCHAR     # 股票代码
stock_name    VARCHAR     # 股票名称
trade_date    DATE        # 交易日期
close         DECIMAL     # 收盘价
adj_factor    DECIMAL     # 复权因子，可选；缺失时按1处理
```

也兼容 `tools/updata_data.py` 生成的 `etf_daily_price` 表，至少需要：

```sql
ts_code / stock_code VARCHAR
trade_date           DATE
close                DECIMAL
```

### 按代码分表结构

表名形如 `510300_SH`、`511260_SH`、`000001_SH`，至少需要：

```sql
trade_date    DATE
close         DECIMAL
```

可选字段：

```sql
name / stock_name
adj_factor
```

## 配置说明

后端配置文件 `backend/.env`：

```ini
SQLITE_DB_PATH=data/market_data.sqlite3 # SQLite行情数据库文件，支持相对项目根目录路径
HOST=0.0.0.0             # 服务监听地址
PORT=8000                # 服务端口
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173 # 允许访问后端的前端来源
```

也可以直接设置 Windows 环境变量。后端实际读取状态可访问：

```text
http://127.0.0.1:8000/api/config/status
```

该接口只返回SQLite数据库路径、文件是否存在等非敏感信息。

## 更新行情数据

```bash
python tools/updata_data.py --start-date 20150101
```

脚本使用AkShare写入 `data/market_data.sqlite3`，无需token。默认不复权；可用 `--adj qfq` 或 `--adj hfq` 指定复权口径。AkShare单次调用默认尝试5次，可通过 `--retries`、`--retry-delay` 调整。

### 每日自动更新

项目内置systemd定时任务，默认每天本机时间21:00增量更新行情。整轮更新失败会再重试3次，每次间隔递增；日志写入 `logs/data_update.log`。

```bash
install -m 0644 deploy/systemd/etf-data-update.service /etc/systemd/system/
install -m 0644 deploy/systemd/etf-data-update.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now etf-data-update.timer
systemctl list-timers etf-data-update.timer
```

手动触发或查看日志：

```bash
systemctl start etf-data-update.service
journalctl -u etf-data-update.service -n 100 --no-pager
tail -f logs/data_update.log
```

常用参数可在 `deploy/systemd/etf-data-update.service` 里调整：`AKSHARE_RETRY_TIMES`、`AKSHARE_RETRY_DELAY`、`ETF_UPDATE_RUN_RETRIES`、`ETF_UPDATE_RUN_RETRY_DELAY`、`ETF_UPDATE_MAX_WORKERS`。

前端默认请求同源 `/api`；开发环境由 `frontend/vite.config.js` 代理到后端 `http://127.0.0.1:8000`。

## 开发计划

- [ ] 支持导出回测报告
- [ ] 添加更多回测指标
- [ ] 增加历史回测记录保存

## License

MIT
