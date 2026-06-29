# 国信证券 xxskills 集成优化方案

> 状态：研究阶段  
> 目标：用国信证券 6 个 skill 替代或补充现有 mootdx/akshare 数据源，解决系统排查报告中的数据质量问题。

---

## 一、已完成工作

1. 在 `tools/guosen-skills/` 安装 6 个 skill（`tools/` 按项目策略不提交）。
2. 新增 `backend/services/guosen/client.py` 统一客户端：
   - 自动区分 `GS_API_KEY` / `COZE_GUOSEN_API_KEY_7627056463827140634`
   - 封装行情、财务、宏观经济、智能选股、基金对比、ETF 筛选调用
   - 已提交到 `main`。
3. 已确认 `query_single_hq` 可连通（网络偶有波动）。

---

## 二、当前数据源问题映射

| 报告问题 | 当前数据源 | 根因 | 拟用 skill |
|---|---|---|---|
| 数据源失败 668 次、realtime_hits=0 | mootdx Quotes | 实时接口初始化失败/网络不可达 | gs-stock-market-query |
| sentiment 响应 4.26s、缓存 4 天 | eastmoney → cache | 外网超时、降级到旧缓存 | gs-stock-market-query |
| hotspots 全 0/null | eastmoney | 接口失败回退到交易所聚合 | gs-stock-market-query |
| sectors stock_count=0 | akshare / TDX blocknew | 板块成分股未加载 | gs-stock-market-query |
| K 线延迟 2 个交易日 | TDX 离线文件 | 本地数据未更新 | gs-stock-market-query |
| F10 finance 多字段 null | mootdx F10 / akshare | 编码/字段稀疏 | gs-stock-financial-query |
| F10 profile 字段过少 | stock_list fallback | 只返回 name/market/industry | gs-stock-financial-query |
| 信号名称“省份+代码” | TDX stock_list | ETF/债券名称占位 | gs-stock-market-query |

---

## 三、分模块集成方案

### 3.1 backend/services/data_provider.py

| 优先级 | 函数 | 改动 | skill |
|---|---|---|---|
| P0 | `fetch_realtime_quotes()` | 优先调 `query_comb_hq`，失败再回退 mootdx | market |
| P0 | `_fetch_realtime_kline()` | 用 `query_past_hq` 补最近 N 日 OHLCV | market |
| P0 | `_get_stock_name_map()` | 占位符名称用 `query_single_hq` 补全 | market |
| P1 | `fetch_market_overview()` | 用 `query_multi_hq` 替换批量 TDX 行情 | market |
| P1 | `fetch_ohlcv()` | 近期数据优先 Guosen，历史用 TDX | market |

### 3.2 backend/api/market.py

| 优先级 | 函数 | 改动 | skill |
|---|---|---|---|
| P0 | `_fetch_market_sentiment()` | 用 `query_multi_hq` 涨跌排名计算涨跌家数，替代 eastmoney | market |
| P0 | `_fetch_hotspots_real()` | 用 `query_multi_hq` 行业/概念排名 + `query_related_comb_hq` 成分股 | market |
| P0 | `_get_sector_component_count()` | 用 `query_related_comb_hq` 获取真实成分股列表 | market |
| P1 | `_fetch_limit_up_ladder()` | 用 `query_multi_hq` 涨停排名 | market |

### 3.3 backend/api/quote.py

| 优先级 | 函数 | 改动 | skill |
|---|---|---|---|
| P0 | `_get_f10()` / `get_f10()` | 用 `query_financial(a_balance/a_income/a_cashflow)` 替换 mootdx F10 | financial |
| P0 | `get_stock_profile()` | 合并 `query_single_hq` + `query_financial` 扩展字段 | market + financial |
| P1 | `get_ohlcv()` | 近期数据用 `query_past_hq` 减少延迟 | market |
| P2 | `get_orderbook()` | mootdx 失败时用 `query_single_hq` 兜底 | market |

### 3.4 backend/api/signals.py

| 优先级 | 函数 | 改动 | skill |
|---|---|---|---|
| P1 | `scan_signals()` | 信号结果中占位符名称用 `query_single_hq` 二次解析 | market |
| P2 | 新增 `/signals/guosen-screen` | 调用 `gs-smart-stock-picking` 并转换结果 | picking |

### 3.5 backend/api/data.py

| 优先级 | 函数 | 改动 | skill |
|---|---|---|---|
| P2 | `data_overview()` | 增加 Guosen 云端源健康检查 | market |
| P2 | `get_stock_list()` | 用 `query_multi_hq` 验证停牌/退市状态 | market |

---

## 四、推荐架构：统一数据源路由

新增 `backend/services/data_router.py`：

```python
class DataSourceRouter:
    """Guosen > mootdx > akshare > cache"""

    def get_quotes(self, symbols: List[str]) -> List[StandardQuote]: ...
    def get_kline(self, symbol: str, period: str, days: int) -> pd.DataFrame: ...
    def get_financial(self, symbol: str) -> Dict: ...
    def get_sector_components(self, sector_code: str) -> List[str]: ...
```

`DataProviderService` 与 `DataPlatformService` 统一通过 `DataSourceRouter` 取数，避免每个 API 自己维护 fallback 链。

---

## 五、环境变量配置

项目根目录建议配置（不提交到 git）：

```bash
# 行情 / 财务 / 宏观经济 / 选股 / 基金对比
export GS_API_KEY="V2V-..."

# ETF 筛选（同一 key，变量名不同）
export COZE_GUOSEN_API_KEY_7627056463827140634="V2V-..."
```

---

## 六、下一步建议

1. **先落地 `backend/services/data_router.py` 骨架**（无业务影响，可立刻提交）。
2. **按 P0 逐个替换**：market.py 的 sentiment / hotspots / sectors 改动最小、收益最大。
3. **quote.py F10 改造**：用 `gs-stock-financial-query` 替换 mootdx F10，解决 finance null 问题。
4. **data_provider.py 实时行情改造**：解决 realtime_hits=0 与 K 线延迟。
5. **持续监控**：新增 `/health` 指标统计 Guosen 命中/失败次数。

---

## 七、风险与注意事项

- **网络稳定性**：Guosen API 偶发 `curl failed`，生产环境需加指数退避重试。
- **调用频次限制**：实时行情单次最多 10 只，多股需分批。
- **市场代码映射**：深圳=0、上海=1、北交所=2，需根据代码前缀自动推断。
- **合规声明**：返回数据仅供展示，不做投资建议。
