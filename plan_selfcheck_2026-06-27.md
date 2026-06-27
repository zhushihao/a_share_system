# 系统自检计划（2026-06-27 17:00）

## 目标
执行 Quant Workbench 系统日常自检，**只排查，不修复**，记录所有问题并生成报告。

## 原子任务

### T1: 后端存活检查
- 目标：确认后端进程在运行，/health 返回正常
- 操作：curl http://127.0.0.1:5889/api/health
- 验证：status==ok, version==1.0.0, checks.tdx_dir==true, checks.database==true
- 记录：状态、版本、时间戳、各项检查结果

### T2: 核心API可用性检查（11个API）
- 目标：逐个调用所有核心API，记录状态码和响应
- API列表：
  1. GET /api/v1/quote/000001（个股行情）
  2. GET /api/v1/watchlist（自选股列表）
  3. GET /api/v1/watchlist/with-quotes（带行情自选股）
  4. GET /api/v1/market/overview（大盘数据）
  5. GET /api/v1/signals（交易信号）
  6. GET /api/v1/data/stocks（股票列表）
  7. GET /api/v1/backtest/engines（回测引擎）
  8. GET /api/v1/ai/status（AI状态）
  9. GET /api/v1/settings（设置）
  10. GET /api/v1/data-platform/status（数据平台状态）
  11. GET /api/v1/quote/000001/history（历史数据）
- 验证：HTTP 200，返回JSON，数据非空
- 记录：每个API的状态码、响应大小、关键字段

### T3: 数据真实性检查
- 目标：验证返回的数据是真实数据，非硬编码/非随机
- 操作：
  1. 调用 /api/v1/quote/000001，检查 close, volume, change_pct 等字段
  2. 调用 /api/v1/market/overview，检查 indices 中的上证指数
  3. 调用 /api/v1/signals，检查信号列表
- 验证：
  - close > 0 且 < 10000（合理范围）
  - volume > 0
  - change_pct 在 -20% 到 +20% 之间（当日合理范围）
  - 日期是最近交易日（2026-06-27 或之前最近交易日）
- 记录：每个数据点的值和判断结果

### T4: 数据时效性检查
- 目标：确认最新数据日期
- 操作：
  1. 从 /api/v1/quote/000001 获取最新日期
  2. 从 /api/v1/market/overview 获取日期
- 验证：
  - 最新日期 >= 2026-06-25（最近2-3个交易日）
- 记录：最新日期、延迟天数、状态（正常/警告）

### T5: 前端构建状态
- 目标：确认前端构建产物是否最新且可构建
- 操作：
  1. 检查 dist/ 目录存在性及文件
  2. 在 frontend_react 目录执行 `npm run build`
  3. 记录构建是否成功、主 chunk 大小、错误信息
- 验证：
  - 构建通过（无 ERROR）
  - 主 chunk（index-*.js）大小 < 300KB gzip
  - index.html 存在
- 记录：构建结果、chunk大小、是否有错误

### T6: 问题汇总与报告生成
- 依赖：T1-T5 全部完成
- 目标：整理所有发现的问题，生成报告
- 操作：
  1. 汇总所有检查结果
  2. 按严重程度分类问题
  3. 生成报告并保存到 reports/selfcheck/SYSTEM_LOOP_CHECK_REPORT_2026-06-27_1700.md
- 验证：报告文件存在，格式正确

## 依赖关系
- T1, T2 可以并行（不同API调用）
- T3, T4 可以并行（不同数据检查）
- T5 独立
- T6 依赖 T1-T5

## 资源限制
- 最多3个并行子代理
- 每个子代理最多30分钟
- 只排查，不修复
