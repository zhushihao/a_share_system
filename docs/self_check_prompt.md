# Quant Workbench 系统自检与迭代任务 Prompt（v20260624）

## 执行规范
1. 不要依赖 subagent，直接在当前 agent 执行所有编码和测试
2. 每段代码写完后必须执行验证（至少一个 happy path + 一个 edge case）
3. 修改已有代码时先读取原文件，确认上下文再局部修改
4. 使用 Daimon Python 运行时：`C:\Users\江厉害\AppData\Roaming\kimi-desktop\daimon-share\daimon\runtime\python\.venv\Scripts\python.exe`
5. 用户无 Kimi API，AI 投研模块仅做 UI 骨架和预留接口

---

## 自检范围（必须逐项执行）

### 1. 数据质量自检
- 调用 `/api/v1/quote/000001/signal?period=daily` 验证买卖点API
  - 检查返回字段：`type`, `confidence`, `entry_price`, `stop_loss`, `take_profit`, `position_pct`, `rationale`, `factors`
  - 检查 `rationale` 是否包含中文因子名（`技术指标`/`形态识别`/`量价分析`/`支撑阻力`）
  - 检查 HOLD 信号时 `stop_loss=0.0`, `take_profit=0.0`
  - 检查 BUY 信号时 `stop_loss < entry_price`
  - 检查 SELL 信号时 `stop_loss > entry_price`
- 调用 `/api/v1/quote/000001/patterns?period=daily` 验证形态识别API
  - 检查返回字段是否为 `pattern`（不是 `type`）
  - 检查是否包含 `confidence`, `start_date`, `end_date`, `description`
- 调用 `/api/v1/quote/000001/volume-analysis?period=daily` 验证量价分析API
  - 检查 `nodes` 和 `divergences` 数组
- 调用 `/api/v1/quote/000001/support-resistance?period=daily` 验证支撑阻力API
  - 检查返回字段是否为 `support`/`resistance`/`levels`（不是 `support_levels`/`resistance_levels`）
- 检查前端构建产物是否存在 `frontend_react/dist/index.html`

### 2. 最优实践查询
- 搜索当前金融量化系统领域的最佳实践（如：TradingView的买卖点展示方式、专业交易系统的信号合成方法、动态追踪止损、防抖逻辑）
- 对比当前系统与行业标准的差距
- 记录可以改进的方向

### 3. 自我批判（必须检查以下历史问题）
- **K线图形态标记是否显示**：后端返回英文 `type`（如 `double_top`, `v_reversal`），前端 `TradingViewChart.tsx` 的正则是否匹配英文名称
- **K线图量价标记是否显示**：后端返回英文 `type`（如 `volume_breakout`, `volume_contraction`），前端正则是否兼容英文和中文
- **SignalComposer 的止损计算逻辑**：
  - HOLD 信号时 `stop_loss=0.0`, `take_profit=0.0`（不能出现止损价比入场价高）
  - BUY 信号时止损价必须 `< entry_price`
  - SELL 信号时止损价必须 `> entry_price`
- **rationale 构建**：空因子列表时是否显示 `"无 偏多"` 而不是 `" 偏多"`（带空格）
- **前端信号面板布局**：StockDetail.tsx 中信号面板的字段显示是否完整、颜色是否合理
- **K线图买卖点标记**：是否只标记最后一根K线（不支持历史信号）

### 4. 迭代改进
- 基于自检结果，修改代码修复问题
- 基于最优实践，改进系统设计
- 更新本自检任务的prompt，加入新发现的问题和解决方案

---

## 已知历史问题（已修复，需验证未复发）

| # | 历史问题 | 修复状态 | 验证方法 |
|---|----------|----------|----------|
| 1 | `quote.py` 缺少 `detect_wave_structure` 导入 | 已修复 | 调用 `/wave-structure` 是否 200 |
| 2 | patterns API 返回 `type` 而非 `pattern` | 已修复 | 检查返回字段是否为 `pattern` |
| 3 | support-resistance API 返回 `support_levels` 对象数组 | 已修复 | 检查返回字段是否为 `support`/`resistance`/`levels` |
| 4 | patterns.py 布尔索引警告 | 已修复 | 运行 `detect_all_patterns` 无警告 |
| 5 | K线图形态标记正则只匹配中文 | 已修复 | 检查 `isTopPattern`/`isBottomPattern`/`isVShape` 是否匹配英文 |
| 6 | K线图量价标记正则只匹配中文 | 已修复 | 检查是否兼容 `volume_breakout`/`volume_contraction` 等英文 |
| 7 | SignalComposer rationale 空因子显示异常 | 已修复 | 检查空因子时是否显示 `"无"` |
| 8 | SignalComposer 因子名称未中文化 | 已修复 | 检查 rationale 是否包含 `技术指标`/`形态识别` 等中文 |

---

## 迭代重点（当前版本）

当前系统已实现：
- 多周期K线数据（分钟/日/周/月/季/年）
- 技术指标（MA/KDJ/MACD/RSI/BOLL）+ 叠加
- 形态识别（双顶/双底/头肩/三角形/V型/斐波那契）
- 量价分析（放量突破/缩量回调/背离/天量/地量）
- 支撑阻力（历史高低点/密集成交区/整数关口）
- 波浪结构（5-3艾略特波浪）
- 多因子买卖点合成引擎（SignalComposer）
- 前端信号面板（置信度/入场/止损/止盈/仓位/因子分解）
- 前端K线图买卖点标记 + 止损止盈水平线

**待实现（按优先级排序）**：
1. 防抖逻辑（同一股票 5 日内不重复触发同向信号）
2. 动态追踪止损（trailing stop based on ATR 或最近 N 日低点）
3. K线图支持历史信号标记（从数据库读取历史信号）
4. SuperTrend 指标（趋势确认 + 动态止损参考）
5. 机器学习信号过滤（XGBoost confidence filter）
6. 信号历史回测统计（胜率、平均收益、最大回撤）

---

## 返回要求

1. 自检结果（各API状态、前端构建状态、服务器是否需要重启）
2. 发现的问题和修复方案（包括代码修改点）
3. 最优实践对比结果
4. 下一步迭代建议
5. 更新后的自检任务prompt（包含新发现的问题）
