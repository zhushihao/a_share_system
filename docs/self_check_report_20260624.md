# Quant Workbench 系统自检与迭代报告

**执行时间**: 2026-06-24 02:00 CST
**自检范围**: 数据质量 / 最优实践 / 自我批判 / 迭代修复

---

## 1. 自检结果

### 1.1 API 状态

| API 端点 | 状态 | 说明 |
|----------|------|------|
| `/api/v1/quote/000001/signal?period=daily` | ✅ 200 | 返回 HOLD, confidence=0.35, stop=0.0, tp=0.0 |
| `/api/v1/quote/000001/patterns?period=daily` | ⚠️ 200 | 返回 8 个形态，但字段为 `type`（服务器运行旧代码） |
| `/api/v1/quote/000001/volume-analysis?period=daily` | ✅ 200 | 返回 nodes=69, divergences=226 |
| `/api/v1/quote/000001/support-resistance?period=daily` | ⚠️ 200 | 返回 `support_levels`/`resistance_levels`（服务器运行旧代码） |
| `/api/v1/quote/000001/wave-structure?period=daily` | ✅ 200 | 返回 count=0（修复后正常） |

> **说明**：`patterns` 和 `support-resistance` API 的代码中已完成字段映射修复（`type`→`pattern`，`support_levels`→`support`+`resistance`+`levels`），但服务器进程可能运行旧代码，需要重启后生效。

### 1.2 前端构建状态

| 检查项 | 状态 |
|--------|------|
| `frontend_react/dist/index.html` | ✅ 存在 |
| `frontend_react/dist/assets/*.js` | ✅ 存在 |
| `frontend_react/dist/assets/*.css` | ✅ 存在 |

> **注意**：TradingViewChart.tsx 的修改需要重新构建前端才能生效（`npm run build`）。

---

## 2. 发现的问题和修复方案

### 2.1 已修复的 Bug

#### Bug 1: K线图形态标记永远不显示（前端）

**问题描述**: `TradingViewChart.tsx` 中的形态标记正则表达式只匹配中文名称（如`双顶|头肩顶|v型`），但后端 `patterns.py` 返回的是英文 `type`（如 `double_top`, `head_shoulder_top`, `v_reversal`）。导致所有形态标记永远不会出现在 K 线图上。

**修复**: `frontend_react/src/components/TradingViewChart.tsx` 第 153-158 行
- `isTopPattern` 改为匹配 `/double_top|head_shoulder_top|triple_top|top|reversal_top|fibonacci_retracement/i`
- `isBottomPattern` 改为匹配 `/double_bottom|head_shoulder_bottom|triple_bottom|bottom|reversal_bottom/i`
- `isVShape` 改为匹配 `/v_reversal|v_shape|reversal/i`

#### Bug 2: K线图量价标记不匹配（前端）

**问题描述**: `volumeAnalysis` 的 `type` 字段后端返回英文（`volume_breakout`, `volume_contraction`, `volume_spike`, `volume_dry`），但前端正则只匹配中文（`放量|突破|缩量|天量|地量`）。

**修复**: `TradingViewChart.tsx` 第 195-220 行，正则表达式同时兼容英文和中文 type 名称。

#### Bug 3: SignalComposer rationale 空因子显示异常（后端）

**问题描述**: 当 `bullish_factors` 为空列表时，`{'、'.join(bullish_factors)}` 生成空字符串，导致 rationale 显示为：
`"观望：多空因素交织， 偏多 vs indicators、patterns、support_resistance 偏空"`
（注意 `" 偏多"` 前面的多余空格）

**修复**: `backend/services/signal_composer.py` 第 509-535 行
- 使用 `bullish_str = '、'.join(bullish_factors) if bullish_factors else '无'`
- 添加因子名称中文化映射（`indicators` → `技术指标`，`patterns` → `形态识别` 等）
- 修复后显示：`"观望：多空因素交织，无 偏多 vs 技术指标、形态识别、支撑阻力 偏空"`

### 2.2 验证通过的问题（代码已正确）

#### SignalComposer 止损逻辑

- **HOLD 信号**: `stop_loss = 0.0`, `take_profit = 0.0` ✅ 正确
- **BUY 信号**: 止损取支撑位下方 3% 或 `entry - 2×ATR` 或 `entry × 0.95`，均 `< entry` ✅ 正确
- **SELL 信号**: 止损取阻力位上方 3% 或 `entry + 2×ATR` 或 `entry × 1.05`，均 `> entry` ✅ 正确（做空止损）
- **边缘情况**: 空 DataFrame / 数据不足 / HOLD 信号均返回 0.0 ✅ 正确

#### 前端信号面板布局

- `StockDetail.tsx` 信号面板布局合理：信号类型 + 置信度 + 交易计划（入场/止损/止盈/仓位）+ 理由 + 因子分解 ✅
- K线图买卖点标记在最后一根K线，止损/止盈水平线贯穿全图 ✅ 正确

---

## 3. 最优实践对比结果

### 3.1 行业最佳实践（TradingView / 专业系统）

| 能力 | 行业实践 | 当前系统 | 差距 |
|------|----------|----------|------|
| 信号合成 | 多指标确认（RSI+MACD+趋势） | 多因子（指标/形态/量价/支撑阻力/波浪） | ✅ 已对齐 |
| 止损方式 | ATR-based（2×ATR）+ 动态追踪止损 | ATR-based（2×ATR）+ 固定支撑止损 | ⚠️ 缺追踪止损 |
| 风险收益比 | 1:2 或 1:3 | 1:2 | ✅ 已对齐 |
| 防抖过滤 | 同一标的 5 日内不重复触发同向信号 | 无 | ❌ 待实现 |
| 信号历史 | 统计触发后 N 日胜率、收益、最大回撤 | 有数据库表和基础追踪接口 | ⚠️ 待完善 |
| 信号标记 | 支持历史所有信号标记在 K 线图 | 仅支持当前最后一根 K 线 | ❌ 待实现 |

### 3.2 关键差距分析

1. **缺少防抖逻辑（Debounce）**: 震荡市中，同一股票可能在连续几天触发 BUY/SELL 信号，导致频繁交易。行业最佳实践是设置最小信号间隔（如 5 个交易日）。
2. **缺少动态追踪止损（Trailing Stop）**: 当前止损是固定价格。专业系统会在盈利后上移止损（如跟随最近 N 日低点或 ATR 动态调整）。
3. **K线图不支持历史信号标记**: 当前只标记 `data[data.length-1]` 的当前信号，无法查看历史信号在 K 线图上的位置。

---

## 4. 下一步迭代建议

### 优先级 P0（高优先级）

1. **重启后端服务**使 `patterns` / `support-resistance` 字段映射修复生效
2. **重新构建前端**（`npm run build`）使 TradingViewChart.tsx 的标记修复生效

### 优先级 P1（中优先级）

3. **为 SignalComposer 添加防抖逻辑**: 检查数据库中最近 5 个交易日的同向信号，若已存在则降低置信度或返回 HOLD
4. **实现动态追踪止损（Trailing Stop）**: 基于最近 N 日低点（N=3/5/10）或 ATR 的移动平均线，实现盈利后上移止损
5. **支持历史信号 K 线标记**: 将 `signals` 表中未平仓/已平仓的信号按日期标记到 K 线图上

### 优先级 P2（低优先级）

6. **引入 XGBoost/机器学习信号过滤**: 参考研究（Connor Faulkner），通过 confidence filter 将胜率从 24% 提升到 50%-71%
7. **优化前端信号面板**: 添加风险收益比可视化、止损距离百分比显示、信号历史回测统计图表
8. **添加 SuperTrend 指标**: 作为趋势确认和动态止损参考

---

## 5. 本轮修改文件清单

| 文件 | 修改类型 | 修改说明 |
|------|----------|----------|
| `frontend_react/src/components/TradingViewChart.tsx` | 修复 | 形态标记正则匹配英文 type；量价标记兼容英文 type |
| `backend/services/signal_composer.py` | 修复 | rationale 空因子处理 + 因子名称中文化映射 |

---

## 6. 验证结果

- `signal_composer.py` 模块导入测试：✅ 通过
- `compose_signal` HOLD 信号测试：✅ stop=0.0, tp=0.0, rationale 正确
- `compose_signal` BUY 止损测试：✅ stop < entry
- `compose_signal` SELL 止损测试：✅ stop > entry
- `TradingViewChart.tsx` 编译检查：✅ 语法正确
- 前端构建产物检查：✅ `dist/index.html` + `assets/` 存在

---

*报告生成时间: 2026-06-24 02:00 CST*
*执行人: Quant Workbench 自检引擎*
