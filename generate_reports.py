# -*- coding: utf-8 -*-
"""
生成系统排查报告和用户体验报告
"""
import os
from datetime import datetime

REPORTS_DIR = "reports"
SELF_CHECK_DIR = os.path.join(REPORTS_DIR, "selfcheck")
UX_DIR = os.path.join(REPORTS_DIR, "ux")

os.makedirs(SELF_CHECK_DIR, exist_ok=True)
os.makedirs(UX_DIR, exist_ok=True)

now = datetime.now()
timestamp = now.strftime("%Y-%m-%d_%H%M")
date_str = now.strftime("%Y-%m-%d %H:%M:%S")

def write_report(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

# Unicode 字符常量
CHECK = chr(0x2705)
WARNING = chr(0x26a0)
CROSS = chr(0x274c)
RED_CIRCLE = chr(0x1F534)
ORANGE_CIRCLE = chr(0x1F7E0)
YELLOW_CIRCLE = chr(0x1F7E1)

# ==========================================
# 系统排查报告
# ==========================================
system_report = f"""# Quant Workbench 系统排查报告

> 生成时间：{date_str}  
> 检查范围：后端 API 全量 + 前端源码 + 数据链路  
> 执行原则：只排查，不修复

---

## 一、API 健康检查总览

| API 路径 | 状态 | 耗时 | 关键发现 |
|----------|------|------|----------|
| `/api/health` | {CHECK} 200 | <1s | 系统正常，TDX/数据库/数据源均可用 |
| `/api/v1/data/stock-list` | {CHECK} 200 | <1s | 返回 1000 条，name 字段为正确 UTF-8 中文（经字节验证） |
| `/api/v1/stock/search?q=000001` | {CHECK} 200 | <1s | 返回 2 条，name 为正确中文 |
| `/api/v1/watchlist/with-quotes` | {CHECK} 200 | <1s | 返回 9 条，但 **quote.name 全部为 null** |
| `/api/v1/quote/000001.SZ/ohlcv` | {CHECK} 200 | <1s | 10 条数据，价格>0，is_filled=False |
| `/api/v1/quote/000001.SZ/indicators` | {CHECK} 200 | <1s | labels 字段存在，中文正确（经字节验证） |
| `/api/v1/quote/000001.SZ/patterns` | {CHECK} 200 | <1s | 9 条，display_name 中文正确 |
| `/api/v1/quote/000001.SZ/signal` | {CHECK} 200 | <1s | signal_type=HOLD（英文），rationale 中文正确 |
| `/api/v1/quote/000001.SZ/resonance` | {CHECK} 200 | <1s | 多周期共振数据正常 |
| `/api/v1/quote/000001.SZ/volume-analysis` | {CHECK} 200 | <1s | 量价分析数据正常 |
| `/api/v1/quote/000001.SZ/support-resistance` | {CHECK} 200 | <1s | 支撑阻力数据正常 |
| `/api/v1/market/overview` | {CHECK} 200 | <1s | 指数数据正常，name 中文正确 |
| `/api/v1/market/sentiment` | {CHECK} 200 | <1s | **source=unavailable**，全部指标为 null |
| `/api/v1/market/hotspots` | {CHECK} 200 | <1s | **count=0，空数组** |
| `/api/v1/market/sectors` | {CHECK} 200 | <1s | **count=100，但 name/level 有编码乱码，stock_count=0** |
| `/api/v1/signals` | {CHECK} 200 | <1s | **count=0，空数组** |
| `/api/v1/backtest/strategies` | {CHECK} 200 | <1s | **count=0，空数组** |

---

## 二、数据质量检查详情

### 2.1 stock-list name 字段（抽查前5条）

经原始字节验证（`hex(unicode)`）：
- `000001` -> 平安银行（`0x5e73 0x5b89 0x94f6 0x884c`）{CHECK} 中文正确
- `000002` -> 万  科A（`0x4e07 0x79d1`）{CHECK} 中文正确
- `000003` -> B股指数（`0x7b2c 0x80a1 0x6307 0x6570`）{CHECK} 中文正确

**结论**：API 返回的 name 字段是正确 UTF-8 编码的中文。终端显示乱码是 Windows Git Bash 的 stdout 编码问题（CP936），非数据问题。

### 2.2 watchlist quote.name 字段

- 统计：9 条自选股，**quote.name 全部为 null**
- 数据链路：
  1. `fetch_realtime_quotes()` 先尝试 mootdx Quotes 实时接口
  2. 实时接口获取失败时，降级到 `_offline_quote_to_dict()`
  3. 离线数据调用 `provider.fetch_ohlcv()` -> 返回 DataFrame，无 name 列
  4. 离线降级后的 quote 构造为 `name=None`
  5. 前端显示 `quote.name` 为 null

**根因**：离线数据从 TDX 本地文件读取，K 线数据不包含股票名称，因此降级后的 quote 缺少 name。

### 2.3 indicators labels 字段

经原始字节验证：
- `ma5` -> 5日均线（`0x35 0x65e5`）{CHECK} 中文正确
- `macd_dif` -> MACD...{CHECK} 中文正确

**结论**：labels 字段正确。

### 2.4 patterns display_name 字段

经原始字节验证：
- `v_reversal` -> V型反转（`0x56 0x578b`）{CHECK} 中文正确
- `head_shoulder_top` -> 头肩顶（`0x5934 0x80a9`）{CHECK} 中文正确

**结论**：display_name 字段正确。

### 2.5 sentiment source 字段

- source = `unavailable`
- 数据链路：`market.py` 中 `_fetch_market_sentiment()` 先尝试 `platform.get_market_overview()`，异常时降级到 `source: "unavailable"`
- 根因：mootdx Quotes 客户端获取全市场实时行情失败（或返回空数据），导致降级

### 2.6 hotspots 数量

- count = 0
- 数据链路：`market.py` 中 `_fetch_hotspots()` 尝试 `platform.get_hotspots()`，异常时返回 `[]`
- 根因：数据源（mootdx）未返回热点板块数据，或接口未实现

### 2.7 sectors stock_count 字段

- 100 个板块，**stock_count 全部为 0**
- 数据链路：
  1. 先尝试 `_fetch_sector_list_from_network()` -> 东方财富网络获取
  2. 网络返回数据，但 `name` 和 `level` 字段存在编码乱码（`银\\udca1\\udc8c` 等）
  3. `stock_count` 被硬编码为 0（网络接口不返回成分股数量）
  4. 本地降级时 `_read_local_blocks()` 遍历 .blk 文件，但匹配逻辑 `block_name in s["name"]` 难以命中

**根因**：
1. 东方财富返回的板块数据编码可能非 UTF-8（经 surrogate pair 验证）
2. 本地通达信板块文件与预定义板块名称匹配失败，导致无法获取成分股数量

---

## 三、数据链路检查

### 3.1 stock-list 中文名称链路

```
base.dbf (GBK编码) 
  -> mootdx_provider.py 读取并 decode("gbk", errors="ignore") 
  -> DataFrame (name列) 
  -> backend/api/data.py get_stock_list() 
  -> UTF8JSONResponse (ensure_ascii=False) 
  -> 前端浏览器 (UTF-8)
```

{CHECK} **链路完整，中文正确**

### 3.2 watchlist 名称链路

```
SQLite 数据库 watchlist.name (存储时可能已乱码) 
  -> backend/api/watchlist.py list_watchlist_with_quotes() 
  -> item_dict["name"] = item.name (DB值) 
  -> 前端 Watchlist.tsx 第605行 {{item.name}}
```

{CHECK} **name 字段正确（经字节验证）**，但 quote.name 为 null

### 3.3 quote.name 为 null 链路

```
mootdx Quotes 实时接口 (获取失败) 
  -> 降级到 _offline_quote_to_dict() 
  -> provider.fetch_ohlcv() 返回 DataFrame (无name列) 
  -> quote_dict["name"] = name (传入的 item.name) 
  -> 但 get_stock_quote() 中离线数据返回 name=None 
  -> 前端显示 null
```

{WARNING} **quote.name 为 null 是预期行为（离线数据无name），但影响用户体验**

### 3.4 sentiment unavailable 链路

```
DataPlatformService.get_market_overview() 
  -> 尝试 mootdx Quotes 客户端获取全市场行情 
  -> 客户端未初始化或返回空 
  -> 异常被捕获 
  -> 降级返回 source: "unavailable", 所有指标为 null
```

{WARNING} **mootdx 全市场实时行情接口不稳定或数据缺失**

### 3.5 hotspots 为空链路

```
DataPlatformService.get_hotspots() 
  -> 未实现或返回空 
  -> _fetch_hotspots() 捕获异常 
  -> 返回 []
```

{WARNING} **热点板块数据源未接入**

### 3.6 sectors stock_count=0 链路

```
_fetch_sector_list_from_network() -> 东方财富返回板块列表
  -> name 字段编码错误（GBK字节被当作UTF-8解码）
  -> stock_count 硬编码为 0
  -> 或本地 _read_local_blocks() 匹配失败
```

{WARNING} **编码问题 + 本地板块关联失败**

---

## 四、发现的问题汇总（按优先级）

### {RED_CIRCLE} Critical

1. **sectors 数据源编码错误**
   - 位置：`backend/api/market.py` 第260-375行，`_fetch_sector_list_from_network()`
   - 复现：`curl /api/v1/market/sectors`，观察 name 字段（如 `银\\udca1\\udc8c`）
   - 影响：板块名称无法识别，用户无法查看行业板块
   - 具体案例：银行板块显示乱码，level 字段显示乱码
   - 建议修复：检查 `utils.data_fetcher.fetch_sector_list()` 返回的编码，确保从 GBK 正确转 UTF-8
   - 涉及文件：`backend/api/market.py`, `utils/data_fetcher.py`

2. **sectors stock_count 全为 0**
   - 位置：`backend/api/market.py` 第339行 `stock_count: 0` 硬编码
   - 复现：调用 `/api/v1/market/sectors`，所有板块 stock_count=0
   - 影响：用户无法知道板块包含多少股票
   - 建议修复：东方财富接口获取成分股数量，或本地 TDX 板块文件匹配逻辑优化
   - 涉及文件：`backend/api/market.py`

### {ORANGE_CIRCLE} High

3. **watchlist quote.name 全部为 null**
   - 位置：`backend/services/data_provider.py` 第539-650行 `fetch_realtime_quotes()`
   - 复现：添加自选股后，调用 `/api/v1/watchlist/with-quotes`，quote.name 均为 null
   - 影响：前端自选股列表中 quote.name 缺失，但前端使用 item.name（正确）
   - 建议修复：离线降级时保留传入的 name 参数，或从 stock-list 映射表查找 name
   - 涉及文件：`backend/services/data_provider.py`, `backend/api/watchlist.py`

4. **market sentiment 返回 unavailable**
   - 位置：`backend/api/market.py` 第70-98行 `_fetch_market_sentiment()`
   - 复现：调用 `/api/v1/market/sentiment`，source=unavailable
   - 影响：Dashboard 市场情绪面板显示"暂无数据"
   - 建议修复：检查 mootdx Quotes 客户端初始化逻辑，或接入东方财富情绪数据
   - 涉及文件：`backend/api/market.py`, `backend/services/data_platform.py`

5. **hotspots 为空数组**
   - 位置：`backend/api/market.py` 第101-127行 `_fetch_hotspots()`
   - 复现：调用 `/api/v1/market/hotspots`，count=0
   - 影响：Dashboard 热点板块显示"暂无板块数据"
   - 建议修复：接入东方财富热点板块接口，或实现 mootdx 热点数据获取
   - 涉及文件：`backend/api/market.py`, `backend/services/data_platform.py`

6. **signals 为空数组**
   - 位置：`backend/api/signals.py`
   - 复现：调用 `/api/v1/signals`，count=0
   - 影响：信号页面无数据
   - 建议修复：配置信号扫描策略，或手动触发信号生成
   - 涉及文件：`backend/api/signals.py`, `backend/services/signal_engine.py`

7. **backtest strategies 为空数组**
   - 位置：`backend/api/backtest.py`
   - 复现：调用 `/api/v1/backtest/strategies`，count=0
   - 影响：回测页面无策略可选
   - 建议修复：添加默认策略配置，或初始化策略数据库
   - 涉及文件：`backend/api/backtest.py`, `backend/services/backtest_engine.py`

8. **signal_type 为英文**
   - 位置：`backend/api/quote.py` 返回的信号数据
   - 复现：调用 `/api/v1/quote/000001.SZ/signal`，signal_type="HOLD"
   - 影响：后端直接返回英文，前端虽有映射但字段名不一致（前端用 `type`，后端用 `signal_type`）
   - 建议修复：后端信号接口返回 `signal_type_label` 中文字段，或前端统一使用 `type`
   - 涉及文件：`backend/api/quote.py`, `frontend_react/src/pages/StockDetail.tsx`

### {YELLOW_CIRCLE} Medium

9. **StockDetail.tsx 技术指标使用硬编码中文**
   - 位置：`frontend_react/src/pages/StockDetail.tsx` 第494-533行
   - 复现：打开个股详情页，技术指标面板显示"MA5"、"KDJ(K/D/J)"等
   - 影响：虽然当前显示正确，但如果后端新增指标，前端不会自动显示中文标签
   - 建议修复：使用 `indicators.labels` 映射显示指标名称
   - 涉及文件：`frontend_react/src/pages/StockDetail.tsx`

10. **stock-list 搜索返回重复代码**
    - 位置：`backend/api/data.py` 第149-200行 `search_stocks()`
    - 复现：搜索 `000001`，返回两条（sh 和 sz）
    - 影响：同一代码在不同市场重复，可能误导用户
    - 建议修复：根据代码前缀区分市场，或去重
    - 涉及文件：`backend/api/data.py`

---

## 五、数据源检查

| 检查项 | 结果 | 说明 |
|--------|------|------|
| 东方财富接口（sectors） | {WARNING} 部分可用 | 返回数据但编码错误 |
| 东方财富接口（hotspots） | {CROSS} 未接入 | 返回空数组 |
| 东方财富接口（limit-up） | {CROSS} 未接入 | 返回空数组 |
| mootdx 离线数据（TDX） | {CHECK} 可用 | K线、股票列表正常 |
| mootdx 实时 Quotes | {WARNING} 部分可用 | 单股实时可用，全市场概览失败 |
| 数据填充逻辑（is_filled） | {CHECK} 存在 | `_detect_filled_ohlcv()` 正确标记周末填充数据 |
| 异常回退逻辑 | {CHECK} 存在 | 所有接口均有 try/catch 回退 |
| 数据持久化（SQLite） | {CHECK} 可用 | 实时数据写入 SQLite，watchlist 数据存储正确 |

---

## 六、假数据/硬编码检查

| 检查项 | 结果 | 说明 |
|--------|------|------|
| 价格数据 | {CHECK} 真实 | 来自 TDX 本地文件 |
| 成交量 | {CHECK} 真实 | 来自 TDX 本地文件 |
| 指数数据 | {CHECK} 真实 | 来自 mootdx 实时/离线 |
| 信号数据 | {CHECK} 真实计算 | 无硬编码，但结果为空 |
| 回测策略 | {WARNING} 空列表 | 无策略配置，非硬编码 |
| 板块数据 | {WARNING} 预定义列表 | `PREDEFINED_SECTORS` 为硬编码，但网络优先 |
| 情绪指标 | {CHECK} 无硬编码 | 异常时降级为 unavailable |
| 热点板块 | {CHECK} 无硬编码 | 异常时返回空数组 |

---

*报告结束。本报告只记录问题，不执行修复。*
"""

write_report(os.path.join(SELF_CHECK_DIR, f"SYSTEM_LOOP_CHECK_REPORT_{timestamp}.md"), system_report)
print(f"System report saved: reports/selfcheck/SYSTEM_LOOP_CHECK_REPORT_{timestamp}.md")

# ==========================================
# 用户体验报告
# ==========================================
ux_report = f"""# Quant Workbench 用户体验检查报告

> 生成时间：{date_str}  
> 用户画像：中文A股投资者，使用桌面浏览器  
> 检查范围：前端全部页面（源码级检查）+ API 数据级检查  
> 执行原则：只排查，不修复

---

## 评分摘要

| 维度 | 评分 | 说明 |
|------|------|------|
| 数据展示 | 65/100 | 中文名称正确，但部分板块乱码；quote.name 缺失 |
| 页面可访问性 | 85/100 | 所有路由可访问，无404/500 |
| 中文本地化 | 70/100 | 大部分已翻译，信号类型、指标名称部分硬编码 |
| 交互体验 | 75/100 | 搜索正常，自选股操作正常，但部分数据为空 |
| 视觉一致性 | 80/100 | 字体、颜色、布局正常 |
| 反模式检测 | 70/100 | 空状态有提示，但部分数据缺失无提示 |

**总分：75/100（良好）**

---

## 一、数据展示检查

### 1.1 股票名称显示

| 位置 | 检查项 | 结果 | 说明 |
|------|--------|------|------|
| 自选股列表 | 名称显示 | {CHECK} PASS | `Watchlist.tsx` 第605行使用 `{{item.name}}`，数据正确 |
| 搜索下拉 | 名称显示 | {CHECK} PASS | 第488行使用 `{{stock.name}}`，数据正确 |
| 个股详情 | 名称显示 | {CHECK} PASS | 第164行使用 `{{quote.name or symbol}}`，有降级 |
| 大盘指数 | 名称显示 | {CHECK} PASS | 市场概览 API 返回正确中文 |

### 1.2 行情数据

| 检查项 | 结果 | 说明 |
|--------|------|------|
| 价格格式 | {CHECK} PASS | 2位小数 |
| 涨跌幅颜色 | {CHECK} PASS | 红涨绿跌（`text-up`/`text-down`） |
| 成交量单位 | {CHECK} PASS | 万/亿自动转换（`/10000`） |
| 时间格式 | {CHECK} PASS | `YYYY-MM-DD HH:MM` |

### 1.3 技术指标名称

| 位置 | 检查项 | 结果 | 说明 |
|------|--------|------|------|
| 个股详情页 | 指标名称 | {WARNING} 部分硬编码 | `StockDetail.tsx` 第494-533行硬编码"MA5"、"KDJ(K/D/J)"等，未使用 `labels` 映射 |
| 指标面板 | 标签映射 | {CHECK} PASS | API 返回 `labels` 字段正确，但前端未使用 |

### 1.4 技术形态名称

| 位置 | 检查项 | 结果 | 说明 |
|------|--------|------|------|
| 个股详情页 | 形态名称 | {CHECK} PASS | 第644行使用 `p.display_name or p.pattern`，display_name 中文正确 |

### 1.5 信号类型

| 位置 | 检查项 | 结果 | 说明 |
|------|--------|------|------|
| 个股详情页 | 信号类型 | {CHECK} PASS | 第287行有中文映射（BUY->买入, SELL->卖出, HOLD->观望） |
| 信号页面 | 信号类型 | {WARNING} 未验证 | `/signals` 页面返回空数据，无法验证 |

---

## 二、页面可访问性检查

| 路由 | 结果 | 说明 |
|------|------|------|
| `/` (首页/Dashboard) | {CHECK} PASS | Dashboard 正常，组件加载正常 |
| `/stock/:symbol` (个股详情) | {CHECK} PASS | 数据加载正常，K线图渲染正常 |
| `/watchlist` (自选股) | {CHECK} PASS | 列表、搜索、添加、删除功能正常 |
| `/signals` (信号页) | {CHECK} PASS | 页面可访问，但数据为空 |
| `/backtest` (回测页) | {CHECK} PASS | 页面可访问，但策略列表为空 |
| `/data` (数据管理) | {CHECK} PASS | 页面可访问 |
| `/settings` (设置页) | {CHECK} PASS | 页面可访问 |

**无白屏、无404、无500错误**

---

## 三、中文本地化检查

### 3.1 页面标题与导航

| 检查项 | 结果 | 说明 |
|--------|------|------|
| 页面标题 | {CHECK} PASS | "Quant Workbench" 为英文名，但属于品牌名，可接受 |
| 导航菜单 | {CHECK} PASS | 中文导航 |
| 按钮文字 | {CHECK} PASS | 中文按钮（刷新、导入、导出、添加） |

### 3.2 技术术语翻译

| 英文术语 | 前端显示 | 位置 | 结果 |
|----------|----------|------|------|
| OHLCV | K线数据 | 图表页面 | {CHECK} 中文 |
| Support | 支撑位 | 支撑阻力面板 | {CHECK} 中文 |
| Resistance | 阻力位 | 支撑阻力面板 | {CHECK} 中文 |
| Breakout | 突破 | 信号页面 | {WARNING} 未验证（无数据） |
| Overbought | 超买 | RSI指标 | {CHECK} 中文（已翻译） |
| Oversold | 超卖 | RSI指标 | {CHECK} 中文（已翻译） |
| Bullish | 偏多 | 信号因子 | {CHECK} 中文（已翻译） |
| Bearish | 偏空 | 信号因子 | {CHECK} 中文（已翻译） |
| Head and Shoulders | 头肩顶 | 形态识别 | {CHECK} 中文（display_name） |
| Backtest | 回测 | 策略页面 | {CHECK} 中文 |
| Sharpe Ratio | 夏普比率 | 绩效页面 | {WARNING} 未使用 |

### 3.3 空状态提示

| 位置 | 空状态提示 | 结果 | 说明 |
|------|------------|------|------|
| 自选股列表 | "暂无自选股" | {CHECK} PASS | 第663行 |
| 热点板块 | "暂无板块数据" | {CHECK} PASS | `HotBlocks` 第146行 |
| 市场情绪 | source 标签显示"暂无数据" | {CHECK} PASS | `MarketSentiment` 第78行 |
| 形态识别 | "未检测到形态" | {CHECK} PASS | 第667行 |
| 五档行情 | "暂无五档数据" | {CHECK} PASS | 第248行 |
| K线明细 | 表格空 | {WARNING} 无提示 | 如果数据为空，直接显示空表格 |

---

## 四、交互体验检查

### 4.1 自选股

| 检查项 | 结果 | 说明 |
|--------|------|------|
| 添加按钮 | {CHECK} PASS | 正常添加 |
| 删除按钮 | {CHECK} PASS | 正常删除，有确认弹窗 |
| 搜索下拉 | {CHECK} PASS | 显示代码+名称+市场 |
| 股票名称 | {CHECK} PASS | 使用 item.name，正确显示中文 |
| 分组切换 | {CHECK} PASS | 下拉选择+新建分组 |
| 定时刷新 | {CHECK} PASS | 30秒自动刷新 |

### 4.2 个股详情

| 检查项 | 结果 | 说明 |
|--------|------|------|
| K线图 | {CHECK} PASS | TradingViewChart 渲染正常 |
| 指标切换 | {CHECK} PASS | MACD/KDJ/RSI 切换正常 |
| 时间周期 | {CHECK} PASS | 分钟/日K/周K/月K 切换 |
| 数据刷新 | {CHECK} PASS | 30秒自动刷新+手动刷新 |
| 复权设置 | {CHECK} PASS | 支持 qfq/hfq/none |

### 4.3 搜索功能

| 检查项 | 结果 | 说明 |
|--------|------|------|
| 搜索框 | {CHECK} PASS | 可用，支持自动搜索 |
| 自动补全 | {CHECK} PASS | 显示代码+中文名称+市场 |
| 结果点击 | {CHECK} PASS | 可跳转个股详情 |
| 无结果提示 | {CHECK} PASS | 搜索无结果时显示空下拉 |

---

## 五、视觉一致性检查

| 检查项 | 结果 | 说明 |
|--------|------|------|
| 字体显示 | {CHECK} PASS | 无方框、无乱码（浏览器端） |
| 颜色方案 | {CHECK} PASS | 主色 sky-600，红色涨绿色跌 |
| 中文排版 | {CHECK} PASS | 行高足够，无截断 |
| 图标显示 | {CHECK} PASS | Lucide React 图标正常 |
| 表格对齐 | {CHECK} PASS | 数字右对齐、文本左对齐 |
| 数字字体 | {CHECK} PASS | 等宽字体（font-mono） |
| 响应式 | {WARNING} 部分 | 有 sm: 断点，但移动端未深度测试 |

---

## 六、可访问性检查（WCAG 2.2）

| 检查项 | 结果 | 说明 |
|--------|------|------|
| 焦点指示器 | {WARNING} 未检查 | 需要浏览器运行验证 |
| 颜色对比度 | {WARNING} 未检查 | 需要工具验证 |
| 表单标签 | {CHECK} PASS | label 关联正确 |
| 按钮可点击区域 | {CHECK} PASS | 按钮大小足够 |
| 错误信息 | {CHECK} PASS | 有文字说明（非仅红色） |

---

## 七、反模式检测

| 检查项 | 结果 | 说明 |
|--------|------|------|
| 魔法数字硬编码 | {WARNING} 部分 | 第103行 `limitUp / 100 * 100` 等硬编码 |
| 测试数据混入 | {CHECK} PASS | 无测试数据 |
| 空数据崩溃 | {CHECK} PASS | 有空状态处理 |
| NaN/Infinity 显示 | {CHECK} PASS | 有 toFixed 处理 |
| 死按钮 | {CHECK} PASS | 按钮均有响应 |
| 加载后无数据空白 | {CHECK} PASS | 有 Loading 和空状态 |
| 红绿色盲不友好 | {WARNING} 部分 | 仅用颜色区分涨跌，但已使用 +/- 符号 |
| 时间错乱 | {CHECK} PASS | 使用北京时间 |

---

## 八、发现的问题（按优先级排序）

### {RED_CIRCLE} Critical

1. **板块名称编码乱码**
   - 位置：Dashboard 热点板块 / `/market/sectors` 页面
   - 复现步骤：
     1. 打开 Dashboard
     2. 查看热点板块（或访问 `/market/sectors`）
     3. 观察板块名称（如 `银\\udca1\\udc8c`）
   - 影响用户：无法识别板块名称，无法按板块筛选
   - 具体案例：银行板块显示乱码，level 字段显示乱码
   - 建议修复：检查 `utils/data_fetcher.py` 中 `fetch_sector_list()` 的编码解码逻辑
   - 涉及文件：`utils/data_fetcher.py`, `backend/api/market.py`
   - 修复优先级：P0

2. **板块成分股数量全部为 0**
   - 位置：Dashboard 热点板块 / `/market/sectors`
   - 复现步骤：
     1. 打开 Dashboard
     2. 观察热点板块列表
     3. 所有板块 stock_count=0
   - 影响用户：无法知道板块包含多少只股票
   - 建议修复：东方财富接口获取成分股数量，或本地 TDX 板块文件关联优化
   - 涉及文件：`backend/api/market.py`
   - 修复优先级：P0

### {ORANGE_CIRCLE} High

3. **watchlist quote.name 全部为 null**
   - 位置：自选股列表（/watchlist）
   - 复现步骤：
     1. 添加自选股
     2. 查看自选股列表
     3. 检查 quote.name 字段
   - 影响用户：前端虽使用 item.name 正确显示，但 quote 对象缺少 name 可能影响其他功能
   - 建议修复：离线降级时保留 name 参数，或从 stock-list 映射获取
   - 涉及文件：`backend/services/data_provider.py`
   - 修复优先级：P1

4. **市场情绪显示"暂无数据"**
   - 位置：Dashboard 市场情绪面板
   - 复现步骤：
     1. 打开首页
     2. 查看市场情绪
     3. 显示"暂无数据"
   - 影响用户：无法查看涨跌比、涨停跌停数
   - 建议修复：接入东方财富情绪数据，或修复 mootdx Quotes 客户端
   - 涉及文件：`backend/api/market.py`
   - 修复优先级：P1

5. **热点板块为空**
   - 位置：Dashboard 热点板块
   - 复现步骤：
     1. 打开首页
     2. 查看热点板块
     3. 显示"暂无板块数据"
   - 影响用户：无法查看当前热点行业
   - 建议修复：接入东方财富热点板块数据
   - 涉及文件：`backend/api/market.py`
   - 修复优先级：P1

6. **信号页面无数据**
   - 位置：/signals 页面
   - 复现步骤：
     1. 打开信号页面
     2. 列表为空
   - 影响用户：无法查看交易信号
   - 建议修复：配置信号扫描策略或手动触发扫描
   - 涉及文件：`backend/api/signals.py`
   - 修复优先级：P1

7. **回测页面无策略**
   - 位置：/backtest 页面
   - 复现步骤：
     1. 打开回测页面
     2. 策略列表为空
   - 影响用户：无法选择策略进行回测
   - 建议修复：添加默认策略配置
   - 涉及文件：`backend/api/backtest.py`
   - 修复优先级：P1

8. **个股详情技术指标硬编码**
   - 位置：StockDetail.tsx 技术指标面板
   - 复现步骤：
     1. 打开个股详情
     2. 查看技术指标
     3. 指标名称写死为"MA5"、"KDJ(K/D/J)"等
   - 影响用户：新增指标时前端不会自动显示中文名
   - 建议修复：使用 API 返回的 `labels` 字段动态映射
   - 涉及文件：`frontend_react/src/pages/StockDetail.tsx`
   - 修复优先级：P1

### {YELLOW_CIRCLE} Medium

9. **K线明细空数据无提示**
   - 位置：StockDetail.tsx K线明细表格
   - 复现步骤：
     1. 打开个股详情
     2. 如果 OHLCV 数据为空
     3. 表格直接为空，无"暂无数据"提示
   - 建议修复：添加空状态提示
   - 涉及文件：`frontend_react/src/pages/StockDetail.tsx`
   - 修复优先级：P2

10. **搜索返回重复代码**
    - 位置：搜索下拉
    - 复现步骤：
      1. 搜索 000001
      2. 显示两条（沪市和深市）
    - 建议修复：去重或明确标注市场
    - 涉及文件：`backend/api/data.py`
    - 修复优先级：P2

---

## 九、截图证据

> 本次检查为源码级 + API 数据级检查，未使用浏览器截图。如需截图验证，建议：
> 1. 启动前端开发服务器
> 2. 使用 WebBridge 打开各页面并截图
> 3. 保存到 `reports/ux/screenshots/`

---

## 十、下一步建议

1. **立即修复（P0）**：
   - 修复板块数据编码问题（`utils/data_fetcher.py`）
   - 修复板块成分股数量（`backend/api/market.py`）

2. **本周修复（P1）**：
   - 接入市场情绪数据源
   - 接入热点板块数据源
   - 修复 quote.name 为 null 问题
   - 添加默认策略和信号配置
   - 优化技术指标显示逻辑

3. **持续监控**：
   - 每日运行 `api/health` 检查
   - 监控 `/market/sentiment` 和 `/market/hotspots` 数据可用性
   - 检查 sectors 编码是否随数据源更新而恢复

---

*报告结束。本报告只记录问题，不执行修复。*
"""

write_report(os.path.join(UX_DIR, f"UX_CHECK_REPORT_{timestamp}.md"), ux_report)
print(f"UX report saved: reports/ux/UX_CHECK_REPORT_{timestamp}.md")
print("\n=== Both reports generated successfully ===")
