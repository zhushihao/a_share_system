# Quant Workbench v1.0

> 本地金融分析工作台 — 基于 FastAPI + React + SQLite + mootdx 离线数据

## 功能概览

| 模块 | 功能 | 状态 |
|------|------|------|
| 行情看板 | 四大指数、市场情绪、热点板块、涨停梯队 | ✅ |
| 自选股中心 | CRUD、分组、指标表格、导入导出 | ✅ |
| 个股分析 | K线、分时、复权、技术指标、TradingView图表 | ✅ |
| 信号中心 | 日线/日内信号扫描、历史复盘、策略模板 | ✅ |
| 回测引擎 | 事件驱动回测、5种预设策略、自定义策略沙箱 | ✅ |
| 数据管理 | 数据概览、诊断、导出、健康检查 | ✅ |
| AI 投研 | 对话界面、快捷模板、上下文注入（预留接口） | ✅ |
| 系统设置 | 数据源、界面、策略、快捷键配置 | ✅ |

## 技术栈

- **后端**: FastAPI + Pydantic + SQLite (aiosqlite) + mootdx
- **前端**: React 18 + TypeScript + Vite + TailwindCSS + TradingView Lightweight Charts
- **数据源**: mootdx 离线数据（通达信 D:/TDX）优先，实时行情降级
- **技术指标**: MA / KDJ / MACD / RSI / BOLL（通达信兼容）

## 快速启动

### 1. 一键启动（推荐）

双击 `start.bat`，自动启动后端 API 服务：

```
API 文档: http://127.0.0.1:5889/docs
健康检查: http://127.0.0.1:5889/api/health
```

### 2. 手动启动后端

```bash
cd backend
python main.py
```

### 3. 手动启动前端（可选）

```bash
cd frontend_react
npm install
npm run dev
# 访问 http://localhost:5173
```

## 环境要求

- Windows 10/11
- Python 3.12+（已包含在 Kimi Desktop 运行时中）
- 通达信金融终端（数据目录默认 D:/TDX）
- Node.js 18+（仅前端开发需要）

## 配置说明

### 通达信数据目录

默认使用 `D:/TDX`，可在以下位置修改：
- 环境变量：`TDX_DIR`
- 系统设置：`backend/config.py` 或前端「设置」页面

### AI 投研（可选）

1. 登录 [Moonshot](https://platform.moonshot.cn/) 获取 API Key
2. 设置环境变量：`KIMI_API_KEY=sk-...`
3. 或在「系统设置」中配置

## 项目结构

```
a_share_system/
├── backend/                 # FastAPI 后端
│   ├── main.py              # 应用入口
│   ├── config.py            # 配置
│   ├── models/              # 数据模型（Pydantic + SQLite）
│   ├── api/                 # API 路由
│   ├── services/            # 业务服务层
│   │   ├── data_provider.py # 行情数据
│   │   ├── indicators.py    # 技术指标
│   │   ├── signal_engine.py # 信号引擎
│   │   ├── backtest_engine.py # 回测引擎
│   │   └── onboarding.py    # 启动引导
│   ├── core/                # 复用旧系统核心模块
│   └── utils/               # 工具函数
├── frontend_react/          # React 前端
│   ├── src/
│   │   ├── pages/           # 页面组件
│   │   ├── components/      # 通用组件
│   │   ├── api/             # API 客户端
│   │   └── stores/          # 状态管理（Zustand）
│   └── package.json
├── tests/                   # 测试脚本
│   └── performance_test.py  # 性能验收测试
├── docs/                    # 文档
│   ├── project_state.md     # 项目状态
│   ├── facts.md             # 技术事实记录
│   └── plan.md              # 整体架构
└── start.bat                # 启动脚本
```

## 性能指标

| 指标 | 目标 | 实测 |
|------|------|------|
| K 线加载 + 指标计算 | < 200ms | ~9ms |
| 50 只自选股指标计算 | < 500ms | ~315ms |
| 市场板块扫描 | < 3000ms | ~11ms |
| 50 只信号扫描 | < 10000ms | ~705ms |

## 信号策略

### 日线信号（7种）
- MA 金叉 / 死叉
- 量价突破（放量创20日新高）
- 量价崩溃（放量跌破20日新低）
- 蔡森 W 底 / 头肩底（简化形态检测）
- 白大右侧交易（MA多头 + MACD金叉）

### 日内信号（3种）
- VWAP 突破
- 放量滞涨
- 开盘八法

### 回测策略（5种）
- 双均线交叉
- MACD 金叉/死叉
- KD 超买超卖
- 蔡森 W 底
- 白大右侧交易
- 自定义策略（沙箱执行）

## 开发规范

- 每段代码写完后必须执行验证（happy path + edge case）
- 复用旧系统 `core/`、`utils/`、`events/` 模块，不破坏现有功能
- 所有新代码放在 `backend/` 和 `frontend_react/` 下
- 修改已有代码时先读取原文件，确认上下文再局部修改

## 许可证

MIT
# Test change
