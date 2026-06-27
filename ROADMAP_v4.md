# A股动量趋势系统 v4.0 - 优化路线图

> 基于最先进AI编程理念的系统性重构计划
> 核心理念：Observability-First, Configuration-Driven, LLM-Augmented, Event-Driven

---

## 当前系统评估（v3.0现状）

```
已完成：
✅ Harness Engineering 核心框架（DAG编排、IO契约、错误策略）
✅ 6个业务模块的 Harness 封装
✅ 端到端流水线验证（5/5通过）
✅ 数据获取修复（指数映射、板块缓存优化）

缺失的现代化能力：
❌ 0个单元测试（无测试覆盖）
❌ 无结构化可观测性（只有print）
❌ 无数据血缘追踪（outputs不知来源）
❌ 无持久化层（内存计算，重启即丢失）
❌ 无智能决策（交通灯是硬编码if-else）
❌ 无缓存策略（每次请求都重新获取）
❌ 无配置热更新（修改YAML需重启）
❌ 无并行扫描（全市场5000+只串行处理）
❌ 无事件驱动（批处理，非响应式）
```

---

## 优化目标：v4.0 架构升级

### 目标1：Observability-First（可观测性优先）— P0

**理念**：在AI时代，系统必须有完整的数据流观测能力，这是调试、优化、信任的基础。

**具体实现**：

```
新增文件：core/observability.py

能力矩阵：
┌─────────────┬─────────────┬─────────────┬─────────────┐
│   日志      │   指标      │   链路追踪   │   数据血缘   │
│  (Logging)  │ (Metrics)   │ (Tracing)   │ (Lineage)   │
├─────────────┼─────────────┼─────────────┼─────────────┤
│ 结构化JSON  │ 延迟/成功率  │ 跨Harness   │ 每个output  │
│ 分级输出    │ 吞吐量      │ 调用链      │ 记录来源    │
│ 上下文关联  │ 自定义指标  │ 瀑布图      │ 影响分析    │
└─────────────┴─────────────┴─────────────┴─────────────┘

关键指标：
- data_fetch_latency_ms（数据获取延迟）
- pattern_scan_rate（型态扫描速度：只/秒）
- sector_calc_accuracy（板块计算准确率 vs 市场真实排名）
- traffic_light_precision（绿灯信号的胜率）
- pipeline_success_rate（流水线成功率）
- context_key_lineage（数据血缘图）
```

**工作量**：约600行，2天

---

### 目标2：测试金字塔（Test Pyramid）— P0

**理念**：AI系统没有测试就是盲飞。需要单元测试、集成测试、端到端测试三层防护。

**具体实现**：

```
目录结构：
tests/
├── unit/
│   ├── test_context.py          # Context 数据操作测试
│   ├── test_harness_base.py     # Harness 基类测试
│   ├── test_dag_builder.py      # DAG 构建测试
│   └── test_data_fetcher.py     # 数据获取测试（Mock）
├── integration/
│   ├── test_pipeline_post_market.py  # 盘后流水线集成测试
│   ├── test_pipeline_pre_market.py   # 盘前流水线集成测试
│   └── test_pipeline_backtest.py     # 回测流水线集成测试
├── fixtures/
│   ├── mock_stock_data.csv      # 模拟K线数据
│   ├── mock_sector_list.csv     # 模拟板块列表
│   └── expected_outputs.json    # 期望输出
└── conftest.py                  # pytest 共享配置

测试策略：
1. 单元测试：纯函数测试（run()的inputs/outputs契约）
2. 集成测试：Pipeline端到端（Mock外部数据源）
3. 性能测试：超时断言（sector_calc < 30s, pattern_scan < 1s/只）
4. 回归测试：每次提交自动运行，失败阻断合并

覆盖率目标：
- core/ 目录：>90%
- harnesses/ 目录：>70%
- utils/ 目录：>60%
```

**工作量**：约1200行测试代码，3天

---

### 目标3：数据持久化与缓存层（Data Persistence & Cache）— P0

**理念**：AI系统必须能记住过去，才能优化未来。内存计算不可扩展。

**具体实现**：

```
新增文件：core/persistence.py, core/cache.py

持久化层设计：
SQLite 数据库：data/system.db

表结构：
┌─────────────────┬──────────────────────────────┐
│    表名          │          字段                 │
├─────────────────┼──────────────────────────────┤
│ stock_klines    │ code, date, open, close, ... │
│ patterns        │ id, code, type, date, conf   │
│ sector_rankings │ date, sector_code, score, ... │
│ traffic_signals │ date, code, signal, reasons   │
│ backtest_results│ date, hypothesis, return, ... │
│ pipeline_runs   │ id, date, mode, success, dur  │
│ harness_metrics │ run_id, name, duration, error  │
└─────────────────┴──────────────────────────────┘

缓存策略（多级缓存）：
L1: 内存缓存（Python dict，同进程内）
L2: 本地文件缓存（data/cache/*.pkl，跨进程）
L3: SQLite（跨会话持久化）

缓存键设计：
- stock:{code}:{start}:{end} -> DataFrame
- sector:{sector_code}:{date} -> SectorResult
- pattern:{code}:{date} -> List[Pattern]
- index:{index_code}:{date} -> DataFrame

TTL策略：
- 个股K线：1天（盘后不变）
- 板块数据：1天
- 型态识别：1天（因为型态依赖历史数据，不频繁变化）
- 实时价格：5分钟
```

**工作量**：约800行，2天

---

### 目标4：智能降级与自修复（Intelligent Resilience）— P1

**理念**：AI系统应该像生物一样自适应——感知环境变化、自动调整策略、从失败中学习。

**具体实现**：

```
新增文件：core/resilience.py

能力：
1. 自适应降级（Adaptive Fallback）
   - 数据源失败时，自动切换替代源（ifind → stock_finance_data → 东方财富）
   - 根据历史成功率动态选择最优源
   - 降级策略记录到数据库，用于后续优化

2. 自诊断（Self-Diagnosis）
   - 每个Harness执行后，自动检查outputs质量
   - 异常检测：空DataFrame、异常值、缺失列
   - 自动触发fallback或告警

3. 重试策略（Intelligent Retry）
   - 指数退避：1s, 2s, 4s, 8s, 16s
   - 断路器模式：连续失败5次，30分钟内不再尝试
   - 抖动随机化：避免所有请求同时重试

4. 数据质量评分（Data Quality Score）
   - 完整性：缺失值比例
   - 时效性：最后更新时间
   - 一致性：多数据源对比
   - 可用性：接口响应时间
```

**工作量**：约600行，2天

---

### 目标5：配置热更新与动态调整（Dynamic Configuration）— P1

**理念**：在AI时代，参数不应该硬编码。系统应该能根据运行时表现自动调整阈值。

**具体实现**：

```
新增文件：core/config_manager.py

能力：
1. 热更新（Hot Reload）
   - 修改 system.yaml 后，系统自动重载，无需重启
   - 使用文件 watch（watchdog）或轮询

2. 分层配置（Layered Config）
   - 默认值（代码内）
   - 系统配置（config/system.yaml）
   - 用户配置（config/user.yaml，覆盖系统）
   - 运行时配置（Context中动态传入）

3. A/B测试配置（Experiment Config）
   - 型态识别阈值：min_for_report 0.65 vs 0.70 vs 0.75
   - 交通灯条件：不同的绿灯判定规则
   - 回测并行运行多组参数，对比胜率/夏普

4. 参数敏感性分析（Sensitivity Analysis）
   - 网格搜索：止损5% vs 7% vs 10% 对回测结果的影响
   - 输出最优参数组合
```

**工作量**：约500行，2天

---

### 目标6：LLM增强决策（LLM-Augmented Decision）— P1（高价值）

**理念**：用LLM替代部分硬编码规则，让系统能解释自己的决策、处理边界情况、学习新知识。

**具体实现**：

```
新增文件：core/llm_agent.py

应用场景：
1. 型态识别去噪（Pattern Quality Scoring）
   - 当前：硬编码阈值（对称度>0.6 → 置信度+0.15）
   - 增强：LLM读取型态特征，输出质量评分（0-100）
   - 提示词："分析以下型态特征，判断是否为有效突破..."

2. 板块生命周期判定（Sector Lifecycle）
   - 当前：score > 60 and 3+2 → 发酵期
   - 增强：LLM综合分析板块新闻、政策、资金流向，给出生命周期判断

3. 交通灯信号解释（Signal Explanation）
   - 当前：红灯 because "跌破止损"
   - 增强：LLM生成自然语言解释（"该股今日跌破止损线3%，因为板块龙头跌停，跟风股情绪恶化..."）

4. 报告生成（Report Generation）
   - 当前：模板填充（Markdown）
   - 增强：LLM生成可读性更强的策略报告，包含市场分析、操作建议、风险提示

5. 异常检测（Anomaly Detection）
   - LLM分析每日数据，发现异常模式（如"某板块连续3日异常放量但价格不涨"）

架构：
- LLM Agent 作为独立 Harness（非阻塞，FALLBACK策略）
- 输入：结构化数据（JSON）
- 输出：增强分析结果（存到 Context.llm.{name}）
- 主流程不依赖LLM，但报告生成使用LLM输出
- 使用本地LLM API（如果可用）或云端API
```

**工作量**：约400行，1.5天

---

### 目标7：全市场并行扫描（MapReduce-Style Parallelization）— P1

**理念**：AI时代的数据处理应该是分布式/并行的，单线程处理5000+只股票是不可接受的。

**具体实现**：

```
新增文件：core/parallel_engine.py

设计：MapReduce 模式

Map Phase：
  输入：股票列表（5000+只）
  分片：按CPU核心数分片（如 16 核 → 每批 312 只）
  并行：每批分配一个进程池（ProcessPoolExecutor）
  输出：{code: patterns}

Reduce Phase：
  合并：所有进程的 outputs 合并到 Context
  去重：全局去噪（跨股票的重复型态）
  排序：全局置信度排序

优化策略：
1. 进程池（ProcessPoolExecutor）- 绕开GIL，适合CPU密集型型态识别
2. 批量数据获取 - 一次请求多只股票的K线（ifind支持多ticker）
3. 分片策略 - 按板块分片，同一板块内股票一起处理（缓存复用）

预期性能：
- 当前：12只/6s = 2只/秒
- 目标：5000只/60s = 83只/秒（提升40x）
```

**工作量**：约600行，2天

---

### 目标8：事件驱动架构（Event-Driven Architecture）— P2

**理念**：从批处理（batch）转向响应式（reactive）。系统应该是事件触发的，而不是定时轮询。

**具体实现**：

```
新增文件：core/event_bus.py

事件类型：
- STOCK_PRICE_UPDATED     # 个股价格更新
- PATTERN_DETECTED        # 型态识别完成
- SECTOR_RANKING_CHANGED  # 板块排名变化
- TRAFFIC_LIGHT_CHANGED   # 信号灯变化
- MARKET_REGIME_CHANGED   # 市场状态变化
- BACKTEST_COMPLETED      # 回测完成

事件流：
  data_fetcher ──STOCK_PRICE_UPDATED──> pattern_recognition
  pattern_recognition ──PATTERN_DETECTED──> traffic_light
  traffic_light ──TRAFFIC_LIGHT_CHANGED──> report_generator
  sector_calculation ──SECTOR_RANKING_CHANGED──> traffic_light

消费者模式：
  - 事件队列（Python queue.Queue）
  - 多消费者（不同Harness订阅不同事件）
  - 事件去重（相同事件合并）
  - 事件持久化（SQLite）

好处：
  1. 实时响应：不需要等到盘后才能扫描
  2. 增量计算：只处理变化的数据
  3. 可扩展：未来可接入消息队列（RabbitMQ/Kafka）
```

**工作量**：约700行，2.5天

---

### 目标9：Cron自动化与任务调度（Task Scheduling）— P2

**理念**：系统应该全自动运行，不需要人工触发。智能调度在正确的时间做正确的事。

**具体实现**：

```
调度任务：
┌────────────┬────────────┬────────────────────────────┐
│ 任务名称    │  执行时间   │ 描述                        │
├────────────┼────────────┼────────────────────────────┤
│ 盘后分析    │ 19:30 daily│ 数据下载→型态→板块→交通灯→报告│
│ 盘前简报    │ 09:15 daily│ 快速加载→交通灯→报告         │
│ 偏差报告    │ 15:30 daily│ 持仓对比→纪律检查→修正建议     │
│ 全市场扫描  │ 19:00 daily│ 5000+只型态扫描（每周一次）    │
│ 回测验证    │ 每周日     │ 历史回测，验证策略有效性       │
│ 数据清理    │ 每月1日    │ 清理过期缓存，压缩数据库       │
└────────────┴────────────┴────────────────────────────┘

调度引擎：
- 使用系统 Cron 工具（已可用）
- 每个任务作为独立 Pipeline 运行
- 任务状态持久化到数据库
- 失败自动重试，告警通知
```

**工作量**：约300行，1天

---

### 目标10：回测引擎升级（Backtest Engine v2）— P2

**理念**：回测是量化系统的生命线。需要完整的信号驱动回测，而不是简化版。

**具体实现**：

```
升级内容：
1. 完整信号驱动
   - 每日交通灯信号序列（不是单日）
   - 买卖信号、止损信号、加仓信号、减仓信号
   - T+1交易延迟模拟

2. 多策略对比
   - 策略A：型态突破买入
   - 策略B：纯动量买入
   - 策略C：板块发酵期买入
   - 策略D：组合策略
   - 对比基准：沪深300 Buy&Hold

3. 风险指标
   - 最大回撤（Max Drawdown）
   - 夏普比率（Sharpe Ratio）
   - 卡玛比率（Calmar Ratio）
   - 索提诺比率（Sortino Ratio）
   - 胜率/盈亏比
   - 平均持仓天数

4. 参数优化
   - 网格搜索：止损阈值、仓位比例、型态置信度
   - 遗传算法：多参数联合优化
   - 输出最优参数组合和帕累托前沿
```

**工作量**：约1000行，3天

---

## 实施路线图

```
Phase 1（2周）：基础设施
├── P0-1: 可观测性系统（Observability）
├── P0-2: 测试金字塔（单元测试+集成测试）
├── P0-3: 数据持久化与缓存层
├── P0-4: 修复现有bug（数据获取、指数映射）
│
Phase 2（2周）：智能增强
├── P1-1: 智能降级与自修复（Resilience）
├── P1-2: 配置热更新与动态调整
├── P1-3: LLM增强决策（型态评分、信号解释、报告生成）
├── P1-4: 全市场并行扫描（MapReduce）
│
Phase 3（1-2周）：自动化与回测
├── P2-1: 事件驱动架构（Event Bus）
├── P2-2: Cron自动化与任务调度
├── P2-3: 回测引擎升级（完整信号驱动+多策略对比）
├── P2-4: 端到端模拟盘验证
```

---

## 预期成果（v4.0）

| 维度 | v3.0 | v4.0（目标） | 提升 |
|------|------|-------------|------|
| 测试覆盖 | 0% | >70% | ∞ |
| 可观测性 | print | 结构化日志+指标+链路追踪 | 质变 |
| 数据持久化 | 内存 | SQLite+多级缓存 | 质变 |
| 处理速度 | 12只/6s | 5000只/60s | 40x |
| 决策能力 | 硬编码 | LLM增强 | 质变 |
| 自动化程度 | 手动运行 | 全自动定时 | 质变 |
| 回测能力 | 简化版 | 完整信号驱动+多策略 | 质变 |
| 系统韧性 | 简单try/catch | 断路器+自适应降级 | 质变 |
| 配置灵活性 | 静态YAML | 热更新+A/B测试 | 质变 |

---

## 下一步建议

**立即可启动**：Phase 1 的 P0-1（可观测性）和 P0-2（测试金字塔）。

这两个是基础中的基础——没有可观测性和测试，后续的优化都无法验证效果。需要我立即开始实施吗？
