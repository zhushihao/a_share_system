=== 系统可用性自检报告 ===
时间: 2026-06-25 02:00:39 CST
检查范围: Quant Workbench 后端API + 前端构建 + 数据真实性 + 数据库完整性

【后端API可用性】
- 基础行情API: OK - HTTP 200 - 返回30条OHLCV，最新close=10.71，high>=low，volume>0，价格非0非极端
- 技术指标API: OK - HTTP 200 - 返回MA/KDJ/MACD/RSI/BOLL/OBV/DMI真实计算值（如MA5=10.72, KDJ_K=26.74, MACD_DIF=-0.068, RSI6=38.29, BOLL_UP=11.37, OBV=-16800881, DMI_PDI=22.97）
- 买卖点合成API: OK - HTTP 200 - 返回HOLD信号，entry_price=10.71（最新收盘价），stop_loss=0, take_profit=0, confidence=0.251，rationale完整，6个factors
- 形态识别API: OK - HTTP 200 - 返回8个patterns，pattern_type/name/position/accuracy/reason字段完整
- 量价分析API: OK - HTTP 200 - 返回30个nodes，node_type/volume/price/timestamp/strength/reason字段完整；31个divergences
- 支撑阻力API: OK - HTTP 200 - 返回support=[2 items]/resistance=[3 items]/levels=[5 items]，价格均>0且合理
- 多周期共振API: OK - HTTP 200 - daily_trend=neutral, weekly_trend=neutral, monthly_trend=neutral, resonance=false, confidence=0.2
- 信号列表API: OK - HTTP 200 - 返回3个真实信号（count=3），非假数据
- 自选股API: OK - HTTP 200 - 返回2个自选股
- 回测策略列表API: OK - HTTP 200 - 返回7个策略，包含signal_composer策略

【数据真实性】
- backend/services/data_provider.py: PASS - 无硬编码stock_list或模拟数据，fetch_realtime_quotes使用mootdx获取真实行情
- backend/services/indicators.py: PASS - calculate_all_indicators基于真实OHLCV计算，无硬编码指标值
- backend/services/signal_composer.py: PASS - compose_signal基于真实指标/形态/量价数据计算，entry_price取自最新收盘价，stop_loss基于支撑/ATR，HOLD时sl=tp=0
- backend/services/patterns.py: PASS - 形态检测基于真实价格数据，无随机生成
- backend/services/volume_analysis.py: PASS - 量价分析基于真实成交量数据
- backend/api/quote.py: PASS - 无mock/假数据返回逻辑，所有API返回真实数据
- frontend_react/src/**/*.tsx: PASS - 无硬编码行情数据，所有数据通过API client获取

【前端构建与可用性】
- 构建产物index.html: PASS - 存在
- 构建产物JS/CSS: PASS - assets/index-DKEvriPs.js (520KB), assets/index-Ba6mUNph.css (22KB)
- 资源路径: PASS - 使用相对路径 ./assets/...
- 静态文件服务: PASS - 后端main.py配置了/assets/路由和catch-all路由
- 前端路由: PASS - 包含/, /watchlist, /stock/:symbol, /quote/:symbol, /signals, /backtest, /ai-research, /settings, /strategy-editor, /data，有404 fallback
- StockDetail页面: PASS - 正确引用fetchSignal和fetchResonance API
- TradingViewChart组件: PASS - 正确接收signal参数，显示买卖点标记、止损/止盈/入场价水平线

【数据库与配置】
- SQLite数据库文件: PASS - 存在，路径 ./data/backend/quant_workbench.db，可读写
- signals表结构: PASS - 包含status/exit_price/pnl_pct/max_pnl_pct/min_pnl_pct等新列
- 数据真实性: PASS - 3个信号记录，价格10.52~11.32（合理），非0/非极端值；2个自选股
- 环境配置: PASS - backend/config.py数据路径正确，TDX_DIR=D:/TDX（硬编码路径，需确保本地存在）

【发现的问题】
1. 数据库历史信号timestamp均为"2026-06-XXT00:00:00"（缺少时分秒）- 低严重 - 不影响功能，当前实时API生成的timestamp包含完整时分秒
2. 前端dist目录缺少vite.svg，index.html引用会导致favicon 404 - 低严重 - 不影响核心交易功能
3. 信号历史密度较低（仅3个信号，全部来自000001）- 低严重 - 由5日防抖机制导致，属于设计行为

【已修复的问题】
- 无严重问题需要立即修复。系统数据真实、API可用、GUI可运行。

【下一步迭代建议】
1. 信号覆盖：增加多股票扫描频率或放宽防抖阈值，提升信号覆盖范围
2. 前端性能：TradingViewChart目前每次依赖变化都重建图表，后续可改用series.update()增量更新
3. 完善favicon：将vite.svg复制到dist目录或修改index.html移除引用
4. 数据源冗余：当前依赖mootdx单一离线数据源，建议增加在线数据源作为降级方案
5. SELL语义优化：A股不支持做空，建议在前端将SELL标记文案从"卖出"改为"卖出/平仓"，减少用户误解
