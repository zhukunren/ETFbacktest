# ETF再均衡回测系统

一个基于 **Vue 3 + FastAPI** 的ETF再均衡回测系统。

## 功能特性

- 🎯 自定义ETF选择和权重配置，ETF列表优先从Tushare获取，失败时读取本地Excel
- 📅 灵活的回测周期选择
- 🔄 多种再均衡频率（不再平衡、月初/末、周初/末）
- 📊 完整的回测指标、净值曲线和000001.SH基准对比
- 💡 清晰的再均衡记录追踪
- 💸 支持买入/卖出交易费率，默认各万分之三
- 💵 ETF无行情期间自动保留对应目标权重为现金，并在回测结果中提示

## 技术栈

### 后端
- FastAPI - 现代Python Web框架
- pandas + numpy - 数据处理和回测计算
- PyMySQL - MySQL数据库连接
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

# 配置数据库（复制 .env.example 为 .env 并修改）
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
3. **设置参数**：选择回测周期、再均衡频率、初始资金、交易费率和基准代码
4. **运行回测**：点击"运行回测"查看结果

## 回测指标

- 总收益率
- 年化收益率
- 最大回撤
- 波动率（年化）
- 夏普比率
- 期末资产
- 再均衡次数

## 数据库要求

系统使用MySQL数据库保存回测行情，支持两类行情结构。ETF选择列表优先使用Tushare
`etf_basic(list_status='L')`（需要配置 `TUSHARE_TOKEN` 或 `TUSHARETOKEN`），无法拉取时读取
`data/ETF列表.xlsx`，不会扫描MySQL表。

### 单表结构

```sql
-- stock_daily_price 表
stock_code    VARCHAR     # 股票代码
stock_name    VARCHAR     # 股票名称
trade_date    DATE        # 交易日期
close         DECIMAL     # 收盘价
adj_factor    DECIMAL     # 复权因子，可选；缺失时按1处理
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
DB_HOST=localhost          # 数据库地址
DB_PORT=3306              # 数据库端口
DB_NAME=etf_data          # 默认ETF行情库
ETF_DB_NAME=etf_data      # ETF按代码分表所在库
INDEX_DB_NAME=stock_data  # 000001.SH等指数行情所在库
MYSQL_USER=root           # 数据库用户，优先于旧变量 DB_USER
MYSQL_PASSWORD=your_password # 数据库密码，优先于旧变量 DB_PASSWORD
TUSHARE_TOKEN=your_tushare_token # Tushare token
HOST=0.0.0.0             # 服务监听地址
PORT=8000                # 服务端口
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173 # 允许访问后端的前端来源
```

也可以直接设置 Windows 环境变量。后端实际读取状态可访问：

```text
http://127.0.0.1:8000/api/config/status
```

该接口只返回数据库、密码、Tushare token等配置是否已设置，不返回数据库地址、用户名、密码或token明文。

前端API地址配置在 `frontend/src/api/client.js`。

## 开发计划

- [ ] 支持导出回测报告
- [ ] 添加更多回测指标
- [ ] 增加历史回测记录保存

## License

MIT
