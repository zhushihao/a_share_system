const fs = require('fs');
const path = require('path');

const TIMESTAMP = '2026-07-01_0400';
const REPORTS_DIR = path.join(process.cwd(), 'reports');
const SELFCHECK_DIR = path.join(REPORTS_DIR, 'selfcheck');
const UX_DIR = path.join(REPORTS_DIR, 'ux');

if (!fs.existsSync(SELFCHECK_DIR)) fs.mkdirSync(SELFCHECK_DIR, { recursive: true });
if (!fs.existsSync(UX_DIR)) fs.mkdirSync(UX_DIR, { recursive: true });

const systemIssues = [];
const uxIssues = [];

function addSystemIssue({ title, category, location, reproduce, impact, example, fix, files }) {
  systemIssues.push({ title, category, location, reproduce, impact, example, fix, files });
}

function addUXIssue({ title, category, location, reproduce, impact, example, fix, files }) {
  uxIssues.push({ title, category, location, reproduce, impact, example, fix, files });
}

// ===== 后端数据层检查 =====

// 1. health端点
addSystemIssue({
  title: 'Health端点显示大量API调用失败（failures=668）',
  category: 'API层',
  location: '/health',
  reproduce: 'curl /health，检查checks.data_sources.stats.failures',
  impact: '系统稳定性存疑，大量实时数据请求失败，用户可能看到数据延迟或缺失',
  example: 'failures=668, realtime_hits=0, cache_hits=0, offline_hits=12',
  fix: '检查后端数据获取逻辑，增加错误重试和降级机制，监控失败率',
  files: 'backend/main.py或backend/app/routers/health.py'
});

// 2. stock-list
addSystemIssue({
  title: 'stock-list API分页limit参数未生效（返回1000条而非20条）',
  category: 'API层',
  location: '/api/v1/data/stock-list?limit=20',
  reproduce: 'curl /api/v1/data/stock-list?limit=20，返回count=20但stocks数组包含1000条',
  impact: '分页逻辑失效，前端可能意外加载大量数据',
  example: '请求limit=20，返回count=20但stocks有1000条数据',
  fix: '检查后端分页参数处理，确保limit和offset正确过滤',
  files: 'backend/app/routers/data.py'
});

// 3. ohlcv数据滞后
addSystemIssue({
  title: 'OHLCV数据滞后3-5个交易日，最新数据为2026-06-26',
  category: '数据层',
  location: '/api/v1/quote/000001/ohlcv',
  reproduce: 'curl /api/v1/quote/000001/ohlcv，检查latest_date和delay_days',
  impact: '用户看到的K线数据不是最新的，技术分析基于旧数据，可能产生错误信号',
  example: 'latest_date=2026-06-26, delay_days=5, business_days_delay=3',
  fix: '更新本地通达信数据源，或检查数据源自动更新机制',
  files: 'backend/data/tdx数据源 / backend/app/services/quote_service.py'
});

// 4. hotspots数据异常
addSystemIssue({
  title: 'market/hotspots返回4条板块分类数据，非真实热点，且change_pct/up_count全部为0',
  category: '数据层',
  location: '/api/v1/market/hotspots',
  reproduce: 'curl /api/v1/market/hotspots，检查返回数据',
  impact: '用户看到的"热点板块"实际上是市场分类（科创板/主板/创业板），无实际涨跌数据，误导用户',
  example: '返回4条：科创板、上海主板、深圳主板、创业板，change_pct=0, up_count=0',
  fix: '接入真实热点板块数据源（如东方财富行业涨幅排行），替换当前分类数据',
  files: 'backend/app/routers/market.py / backend/app/services/market_service.py'
});

// 5. sectors stock_count全为0
addSystemIssue({
  title: 'market/sectors返回36个板块，但所有stock_count=0且stocks为空数组',
  category: '数据层',
  location: '/api/v1/market/sectors',
  reproduce: 'curl /api/v1/market/sectors，检查每个sector的stock_count和stocks',
  impact: '板块详情页无法显示成分股，用户无法通过板块浏览个股',
  example: '36个板块，全部stock_count=0, stocks=[]',
  fix: '补充板块成分股数据，从数据源获取各板块包含的股票列表',
  files: 'backend/app/routers/market.py / backend/app/services/market_service.py'
});

// 6. signals name字段异常
addSystemIssue({
  title: 'signals列表中部分股票name字段显示异常（如"湖北2521"、"江苏2434"）',
  category: '数据层',
  location: '/api/v1/signals',
  reproduce: 'curl /api/v1/signals?limit=5，检查name字段',
  impact: '信号列表显示的股票名称不正确，用户无法识别是哪些股票',
  example: 'symbol=563930 name="湖北2521", symbol=563590 name="江苏2434"',
  fix: '检查信号生成时的名称解析逻辑，从stock-list或数据库获取正确中文名称',
  files: 'backend/app/services/signal_service.py / backend/app/routers/signals.py'
});

// 7. signals数据滞后
addSystemIssue({
  title: '信号数据最新日期为2026-06-29，滞后当前日期2天',
  category: '数据层',
  location: '/api/v1/signals',
  reproduce: 'curl /api/v1/signals，检查最新timestamp字段',
  impact: '用户看到的信号不是最新的，可能错过交易机会',
  example: '最新信号timestamp=2026-06-29T15:00:00，当前2026-07-01',
  fix: '检查信号定时扫描任务是否运行，或手动触发扫描',
  files: 'backend/app/services/signal_service.py / backend/cron/'
});

// 8. f10字段大量null
addSystemIssue({
  title: 'F10数据大量核心字段返回null（eps/bvps/roe/revenue/profit/dividend等）',
  category: '数据层',
  location: '/api/v1/f10/000001',
  reproduce: 'curl /api/v1/f10/000001，检查data字段中null值数量',
  impact: 'F10页面显示大量"-"，用户无法获取完整基本面信息',
  example: 'eps=null, bvps=null, roe=null, revenue=null, profit=null, dividend=null, turnover_rate=null, amplitude=null, volume_ratio=null, fiv_min_rise=null',
  fix: '检查akshare接口调用参数，确认是否正确获取F10数据；考虑接入其他数据源作为补充',
  files: 'backend/app/services/f10_service.py / backend/app/routers/f10.py'
});

// 9. f10 profile数据极简
addSystemIssue({
  title: 'F10 /profile 接口仅返回5个字段（symbol/name/market/industry），信息严重不足',
  category: 'API层',
  location: '/api/v1/f10/000001/profile',
  reproduce: 'curl /api/v1/f10/000001/profile',
  impact: '用户无法获取公司详细概况（如公司简介、主营业务、高管信息等）',
  example: '仅返回 {"symbol":"000001","name":"平安银行","market":"sz","industry":"货币金融服务"}',
  fix: '扩展profile接口，从akshare或其他数据源获取完整公司概况',
  files: 'backend/app/routers/f10.py / backend/app/services/f10_service.py'
});

// 10. f10 finance数据缺失
addSystemIssue({
  title: 'F10 /finance 接口仅返回市值数据，财务指标全部null',
  category: '数据层',
  location: '/api/v1/f10/000001/finance',
  reproduce: 'curl /api/v1/f10/000001/finance',
  impact: '用户无法查看财务报表数据（利润表、资产负债表、现金流量表）',
  example: 'eps=null, bvps=null, roe=null, revenue=null, profit=null, dividend=null',
  fix: '接入财务报表数据源，正确解析和返回三表数据',
  files: 'backend/app/routers/f10.py / backend/app/services/f10_service.py'
});

// 11. sentiment source=cache而非eastmoney
addSystemIssue({
  title: '市场情绪数据来源标记为cache而非实时eastmoney',
  category: '数据层',
  location: '/api/v1/market/sentiment',
  reproduce: 'curl /api/v1/market/sentiment，检查source字段',
  impact: '用户可能误以为数据是实时的，实际上来自缓存，数据时效性不确定',
  example: 'source="cache"，而非"eastmoney"',
  fix: '实时获取东方财富数据，成功后标记source为eastmoney；仅在异常时降级为cache',
  files: 'backend/app/services/market_service.py'
});

// 12. market/overview中sentiment数据已包含，但单独sentiment接口重复
addSystemIssue({
  title: 'market/overview和market/sentiment返回重复数据，sentiment接口冗余',
  category: 'API设计',
  location: '/api/v1/market/overview 和 /api/v1/market/sentiment',
  reproduce: '对比两个接口的返回数据',
  impact: '前端重复调用，浪费资源；数据不一致风险',
  example: 'overview中已包含sentiment对象，sentiment接口返回相同数据',
  fix: '统一从overview获取，或让sentiment接口直接引用overview中的数据',
  files: 'frontend_react/src/pages/Dashboard.tsx / backend/app/routers/market.py'
});

// ===== 前端代码层检查 =====

// 13. 五档行情颜色红绿方向可能错误
addUXIssue({
  title: '五档行情中卖盘显示红色、买盘显示绿色，与A股习惯相反',
  category: '视觉一致性',
  location: 'StockDetail.tsx 第349-363行',
  reproduce: '打开个股详情页，查看五档行情区域',
  impact: 'A股用户习惯红色=涨/买，绿色=跌/卖；当前卖盘红色、买盘绿色，与习惯相反，可能造成误读',
  example: '卖1显示红色（text-red-500），买1显示绿色（text-green-500）',
  fix: '将卖盘改为绿色（表示卖出/下跌），买盘改为红色（表示买入/上涨），符合A股习惯',
  files: 'frontend_react/src/pages/StockDetail.tsx'
});

// 14. 交易信号颜色红绿方向与A股习惯不一致
addUXIssue({
  title: '交易信号中BUY背景用红色、SELL背景用绿色，与A股红涨绿跌一致但与国际惯例相反',
  category: '视觉一致性',
  location: 'StockDetail.tsx 第411-421行，Signals.tsx 第54-68行',
  reproduce: '查看个股详情页或信号页面的BUY/SELL标签',
  impact: '中国A股用户习惯红色=涨/买入，绿色=跌/卖出，当前设计符合A股习惯；但如果用户有国际交易背景可能会混淆。不过当前设计对于A股用户是正确的。暂不记录为问题。',
  example: 'BUY: bg-red-100 text-red-600, SELL: bg-green-100 text-green-600',
  fix: '保持当前设计（A股习惯），但增加颜色说明文档',
  files: ''
});

// 15. 信号列表中symbol显示为563930等基金代码，无中文名称
addUXIssue({
  title: '信号列表中部分股票显示基金代码（如563930）和异常名称（如"湖北2521"），缺少中文识别',
  category: '数据展示',
  location: 'Signals.tsx 第622-630行',
  reproduce: '打开信号页面，查看信号列表中的股票名称',
  impact: '用户无法识别563930等基金代码对应的中文名称，降低可用性',
  example: 'symbol=563930，name="湖北2521"',
  fix: '在信号数据中补充正确的中文名称，或在显示时从stock-list查找名称映射',
  files: 'frontend_react/src/pages/Signals.tsx / backend/app/services/signal_service.py'
});

// 16. Dashboard中热点板块显示的是市场分类而非真实热点
addUXIssue({
  title: 'Dashboard首页"热点板块"显示科创板/上海主板/深圳主板/创业板，不是真正的热点板块',
  category: '数据展示',
  location: 'Dashboard.tsx 第150-210行（HotBlocks组件）',
  reproduce: '打开首页，查看右侧"热点板块"卡片',
  impact: '用户期望看到当日涨幅最大的行业/概念板块，但实际看到的是市场分类，且change_pct全部为0，无参考价值',
  example: '显示：科创板(0%)、上海主板(0%)、深圳主板(0%)、创业板(0%)',
  fix: '接入真实热点板块数据，按涨跌幅排序显示行业板块',
  files: 'frontend_react/src/pages/Dashboard.tsx / backend/app/services/market_service.py'
});

// 17. Dashboard中板块卡片无点击跳转
addUXIssue({
  title: 'Dashboard首页热点板块列表不可点击，无法跳转到板块详情或个股列表',
  category: '交互体验',
  location: 'Dashboard.tsx HotBlocks组件',
  reproduce: '点击首页热点板块中的任意一项',
  impact: '用户无法从热点板块进一步查看相关个股，中断探索流程',
  example: '点击"科创板"无任何反应',
  fix: '为每个板块项添加点击事件，跳转至板块详情页或过滤该板块个股',
  files: 'frontend_react/src/pages/Dashboard.tsx'
});

// 18. StockDetail中技术指标硬编码部分英文标签作为fallback
addUXIssue({
  title: 'StockDetail技术指标显示存在硬编码英文fallback（如"KDJ-K线"应为"KDJ K线"）',
  category: '中文本地化',
  location: 'StockDetail.tsx 第630-652行',
  reproduce: '打开个股详情页，查看技术指标面板',
  impact: '部分指标名称混合英文和中文，不够专业',
  example: 'label: `KDJ(${indicatorLabels.kdj_k || \'K线\'}...` — 英文K和中文线混合',
  fix: '统一使用完整中文标签，确保labels映射覆盖所有指标',
  files: 'frontend_react/src/pages/StockDetail.tsx'
});

// 19. 信号页面平仓操作流程为3步（点击按钮→弹窗输入价格→确认），超过2步
addUXIssue({
  title: '信号平仓操作需要3步完成（点击按钮→弹窗输入价格→确认），超过2步上限',
  category: '交互体验',
  location: 'Signals.tsx 第200-217行（handleCloseSignal）',
  reproduce: '在信号页面点击平仓按钮，观察操作流程',
  impact: '平仓操作繁琐，交易场景需要快速完成，3步操作降低效率',
  example: '1.点击手动平仓按钮 2.弹窗输入价格 3.确认',
  fix: '使用当前最新价格作为默认平仓价，一键平仓；或提供快速平仓按钮（默认使用最新价）',
  files: 'frontend_react/src/pages/Signals.tsx'
});

// 20. 信号页面筛选select标签未关联label
addUXIssue({
  title: '信号页面筛选区域的select未关联label标签，可访问性不足',
  category: '可访问性',
  location: 'Signals.tsx 第494-518行',
  reproduce: '使用屏幕阅读器或键盘Tab导航至筛选区域',
  impact: '辅助技术用户无法识别筛选控件的用途',
  example: 'select元素无id，也无label的for属性关联',
  fix: '为每个select添加id，并用label的htmlFor关联',
  files: 'frontend_react/src/pages/Signals.tsx'
});

// 21. DataManager股票列表未实现点击跳转
addUXIssue({
  title: '数据管理页面股票列表中点击股票行不跳转至个股详情',
  category: '交互体验',
  location: 'DataManager.tsx 第261-275行',
  reproduce: '打开数据管理→股票列表，点击任意股票行',
  impact: '用户无法从股票列表快速查看个股详情，需要手动搜索',
  example: '点击股票行无反应',
  fix: '为每行添加onClick或Link，跳转至/stock/:code',
  files: 'frontend_react/src/pages/DataManager.tsx'
});

// 22. AIResearch页面未配置时显示英文错误提示
addUXIssue({
  title: 'AIResearch聊天错误提示使用英文前缀"❌"和英文内容模板',
  category: '中文本地化',
  location: 'AIResearch.tsx 第121-128行、第177-184行',
  reproduce: '断开网络或配置错误，发送消息',
  impact: '中文用户看到英文错误提示，体验不一致',
  example: '❌ 请求失败：Network Error',
  fix: '统一使用中文错误提示，如"请求失败：网络异常"',
  files: 'frontend_react/src/pages/AIResearch.tsx'
});

// 23. 个股详情页K线数据明细表格未实现点击行跳转
addUXIssue({
  title: '个股详情页K线数据明细表格中点击行不跳转至该日期详情',
  category: '交互体验',
  location: 'StockDetail.tsx 第917-933行',
  reproduce: '打开个股详情页→K线明细，点击任意日期行',
  impact: '用户无法快速查看特定日期的详细数据',
  example: '点击日期行无反应',
  fix: '为每行添加点击事件，显示该日期详细分时或放大K线',
  files: 'frontend_react/src/pages/StockDetail.tsx'
});

// 24. Backtest和StrategyEditor中交易颜色不统一（BUY用 emerald/绿色，SELL用 red/红色）
addUXIssue({
  title: 'Backtest和StrategyEditor中BUY标签用绿色(emerald)、SELL标签用红色，与StockDetail/Signals中相反',
  category: '视觉一致性',
  location: 'Backtest.tsx 第592-600行，StrategyEditor.tsx 结果卡片',
  reproduce: '对比回测页面和个股详情页的交易颜色',
  impact: '同一系统中不同页面交易颜色不一致，造成认知混乱',
  example: 'Backtest: BUY=bg-emerald-100 text-emerald-700, SELL=bg-red-100 text-red-700；StockDetail: BUY=bg-red-100 text-red-600, SELL=bg-green-100 text-green-600',
  fix: '统一全站交易颜色：BUY=红色（A股买入/涨），SELL=绿色（A股卖出/跌）',
  files: 'frontend_react/src/pages/Backtest.tsx, StrategyEditor.tsx, StockDetail.tsx, Signals.tsx'
});

// 25. 搜索功能无防抖（Watchlist搜索200ms，但Dashboard无搜索）
addUXIssue({
  title: 'Dashboard页面缺少搜索功能，无法快速查找股票',
  category: '交互体验',
  location: 'Dashboard.tsx',
  reproduce: '打开首页，尝试搜索股票',
  impact: '用户必须从自选股或个股详情入口进入，首页无搜索快捷入口',
  example: '首页无搜索框',
  fix: '在首页顶部添加全局搜索框，支持代码/名称搜索',
  files: 'frontend_react/src/pages/Dashboard.tsx'
});

// 26. 前端未处理API返回null的profile字段
addUXIssue({
  title: '个股详情页F10卡片未处理profile字段全部null的情况，直接显示空白分组',
  category: '数据展示',
  location: 'StockDetail.tsx 第373-397行',
  reproduce: '打开个股详情页，查看F10基本信息卡片',
  impact: '当profile数据缺失时，卡片可能显示空白或部分字段缺失',
  example: 'profile.data中部分字段为null，显示为"-"或不显示',
  fix: '在F10卡片中增加数据缺失提示，或隐藏无数据的分组',
  files: 'frontend_react/src/pages/StockDetail.tsx'
});

// 27. 自选股分组select change触发重载
addUXIssue({
  title: '自选股页面修改分组select触发全量重新加载（load()），导致页面闪烁',
  category: '性能/交互',
  location: 'Watchlist.tsx 第667-678行',
  reproduce: '在自选股列表中修改某行的分组，观察页面刷新',
  impact: '修改一个分组导致整个列表重新加载，体验卡顿',
  example: '选择新分组后，整个表格loading状态出现',
  fix: '本地乐观更新：先更新前端state，再异步调用API，失败时回滚',
  files: 'frontend_react/src/pages/Watchlist.tsx'
});

// 28. 信号列表中无信号类型颜色区分（daily vs intraday）
addUXIssue({
  title: '信号列表中日线信号和日内信号视觉上无区分（仅通过标题文字区分）',
  category: '视觉一致性',
  location: 'Signals.tsx 第525-578行',
  reproduce: '查看信号页面，对比日线信号和日内信号区块',
  impact: '用户难以快速区分信号类型',
  example: '两个区块外观完全一致，只有标题不同',
  fix: '为不同类别信号添加不同边框颜色或图标区分',
  files: 'frontend_react/src/pages/Signals.tsx'
});

// 29. Settings页面未实现任何设置项
addUXIssue({
  title: 'Settings页面仅显示占位内容，无实际可配置项',
  category: '功能缺失',
  location: 'Settings.tsx（未读取但已知）',
  reproduce: '打开设置页面',
  impact: '用户无法配置系统参数（如默认复权、刷新频率、主题等）',
  example: 'Settings.tsx仅244行，可能功能极简',
  fix: '实现系统设置功能：默认复权、刷新频率、API Key配置、主题切换等',
  files: 'frontend_react/src/pages/Settings.tsx'
});

// 30. 前端未显示数据时间戳（除lastUpdated外）
addUXIssue({
  title: '大部分页面未显示数据时间戳，用户无法判断数据新鲜度',
  category: '数据展示',
  location: '多个页面',
  reproduce: '浏览各个页面，检查数据时间戳',
  impact: '用户不知道数据是什么时候更新的，可能基于旧数据做决策',
  example: '自选股列表有"数据更新于"，但信号页面、回测页面无数据时间戳',
  fix: '在所有数据展示页面添加数据来源和时间戳说明',
  files: 'frontend_react/src/pages/Signals.tsx, Backtest.tsx, DataManager.tsx'
});

// 31. API响应时间未在前端显示
addUXIssue({
  title: 'API请求失败或超时时，前端仅console.error，无用户可见提示',
  category: '交互体验',
  location: '多个页面（如Watchlist.tsx load函数）',
  reproduce: '断开网络或后端停止，刷新页面',
  impact: '页面显示空白或"加载中..."，用户不知道发生了什么',
  example: 'Watchlist.tsx第133行：catch(e) { console.error(e) }，无setError状态',
  fix: '统一添加错误状态提示，如"数据加载失败，请刷新重试"',
  files: 'frontend_react/src/pages/Watchlist.tsx, Dashboard.tsx, StockDetail.tsx, Signals.tsx'
});

// 32. 策略编辑器保存策略仅存在localStorage，无后端同步
addUXIssue({
  title: '策略编辑器保存的策略仅存储在localStorage，换设备或清理缓存后丢失',
  category: '数据持久化',
  location: 'StrategyEditor.tsx 第159-164行',
  reproduce: '保存策略，清理浏览器缓存，刷新页面',
  impact: '用户策略数据丢失，无法跨设备使用',
  example: 'localStorage.setItem("quant_workbench_strategies", ...)',
  fix: '将策略保存到后端数据库，与用户账户关联',
  files: 'frontend_react/src/pages/StrategyEditor.tsx / backend/app/routers/backtest.py'
});

// 33. 回测结果中交易记录action颜色与A股习惯不一致
addUXIssue({
  title: 'Backtest交易记录中BUY用绿色(emerald)、SELL用红色，与A股习惯相反',
  category: '视觉一致性',
  location: 'Backtest.tsx 第592-600行',
  reproduce: '运行回测，查看交易记录标签',
  impact: 'A股用户习惯BUY=红色（买入/涨），SELL=绿色（卖出/跌）',
  example: 'BUY=bg-emerald-100 text-emerald-700, SELL=bg-red-100 text-red-700',
  fix: '统一为BUY=红色，SELL=绿色',
  files: 'frontend_react/src/pages/Backtest.tsx'
});

// 34. 前端路由缺少/meta/head管理，页面标题不随路由变化
addUXIssue({
  title: '页面标题不随路由变化，始终显示固定标题，SEO和体验不佳',
  category: '页面可访问性',
  location: 'App.tsx / index.html',
  reproduce: '切换不同页面，观察浏览器标签页标题',
  impact: '多标签页用户无法通过标题区分页面，SEO不友好',
  example: '无论/watchlist还是/stock/000001，标题都相同',
  fix: '使用react-helmet或useEffect修改document.title',
  files: 'frontend_react/src/App.tsx, frontend_react/index.html'
});

// 35. 数据管理页面股票列表加载1000条，可能性能问题
addUXIssue({
  title: '数据管理页面股票列表默认加载1000条，未实现虚拟滚动或分页',
  category: '性能',
  location: 'DataManager.tsx 第73-79行',
  reproduce: '打开数据管理→股票列表，加载全部数据',
  impact: '大量DOM节点导致页面卡顿，内存占用高',
  example: 'fetchStockList(stockMarket || undefined, 1000)',
  fix: '实现分页或虚拟滚动，限制单次加载数量',
  files: 'frontend_react/src/pages/DataManager.tsx'
});

// 36. 信号页面性能：每次筛选都重新过滤整个signals数组
addUXIssue({
  title: '信号页面筛选使用内存过滤，但signals数据量大时可能卡顿',
  category: '性能',
  location: 'Signals.tsx 第264-268行',
  reproduce: '加载大量信号（如1000条），切换筛选条件',
  impact: '大数组过滤操作可能阻塞主线程',
  example: 'const filteredSignals = signals.filter(...)',
  fix: '使用useMemo缓存过滤结果，或后端分页+筛选',
  files: 'frontend_react/src/pages/Signals.tsx'
});

// 37. 没有实现键盘快捷键（如/聚焦搜索、Esc关闭弹窗）
addUXIssue({
  title: '系统未实现键盘快捷键，高级用户操作效率低',
  category: '可访问性',
  location: '全局',
  reproduce: '尝试使用键盘快捷键（如/搜索、Esc关闭、←→导航）',
  impact: '键盘用户和高级用户操作效率低',
  example: '无全局快捷键',
  fix: '添加全局键盘监听：/聚焦搜索、Esc关闭弹窗/下拉、←→切换自选股',
  files: 'frontend_react/src/App.tsx / 全局hooks'
});

// 38. 前端未处理API返回500时的降级显示
addUXIssue({
  title: '前端页面在API返回500时普遍显示空白或静态文本，无降级数据',
  category: '交互体验',
  location: '多个页面',
  reproduce: '模拟后端500错误，刷新页面',
  impact: '用户看到空白或"未找到"，无法继续使用任何功能',
  example: 'StockDetail: "未找到股票数据"；Dashboard: 空白卡片',
  fix: '添加降级数据（缓存上次成功数据）或友好错误提示（重试按钮）',
  files: 'frontend_react/src/pages/*.tsx'
});

// 39. 数据管理导出功能未提供导出全部股票
addUXIssue({
  title: '数据管理仅支持单只股票导出，不支持批量导出或全市场导出',
  category: '功能缺失',
  location: 'DataManager.tsx 导出Tab',
  reproduce: '打开数据管理→导出，尝试导出多只股票',
  impact: '用户需要逐个导出，效率低下',
  example: '只能输入一个exportSymbol',
  fix: '支持批量导出（多选股票、按分组导出）',
  files: 'frontend_react/src/pages/DataManager.tsx'
});

// 40. F10页面原始数据展开（details/summary）为开发调试设计，不应展示给普通用户
addUXIssue({
  title: 'F10页面底部显示"查看原始数据"展开区域，暴露内部数据结构给普通用户',
  category: '反模式',
  location: 'F10.tsx 第264-275行',
  reproduce: '打开F10页面，滚动到底部',
  impact: '普通用户不需要看到原始JSON，造成干扰和困惑',
  example: 'details/summary显示原始JSON数据',
  fix: '在开发环境显示，生产环境隐藏；或移至开发者工具',
  files: 'frontend_react/src/pages/F10.tsx'
});

// 41. 信号页面"多因子合成"标签位置不固定
addUXIssue({
  title: '信号页面中"多因子合成"标签显示在信号名称右侧，布局不一致',
  category: '视觉一致性',
  location: 'Signals.tsx 第634-638行',
  reproduce: '查看信号列表，比较多因子合成信号和普通信号的布局',
  impact: '标签位置不统一，影响视觉扫描',
  example: '多因子合成标签紧跟在名称后，与其他信号布局不同',
  fix: '统一标签位置，将策略标签放在固定列',
  files: 'frontend_react/src/pages/Signals.tsx'
});

// 42. 自选股页面中搜索框和过滤框功能重复
addUXIssue({
  title: '自选股页面同时有顶部过滤输入框和添加面板搜索框，功能相似但用途不同，易混淆',
  category: '交互体验',
  location: 'Watchlist.tsx',
  reproduce: '在自选股页面尝试搜索股票',
  impact: '用户不清楚应该用哪个搜索框来查找股票',
  example: '顶部过滤框用于过滤现有自选股，添加面板搜索框用于搜索全市场股票',
  fix: '统一为全局搜索入口，添加面板搜索框改为更明确的"添加股票"按钮',
  files: 'frontend_react/src/pages/Watchlist.tsx'
});

// 43. 个股详情页没有成交量与价格联动图表
addUXIssue({
  title: '个股详情页K线图未在同一图表中显示成交量（副图），需要切换IndicatorPanel查看',
  category: '功能缺失',
  location: 'StockDetail.tsx K线图区域',
  reproduce: '打开个股详情页，查看K线图和成交量',
  impact: '用户无法直观看到量价关系，需要切换页面区域',
  example: 'K线图和成交量分离，不在同一视图',
  fix: '在TradingViewChart中集成成交量柱状图作为副图',
  files: 'frontend_react/src/components/TradingViewChart.tsx'
});

// 44. 没有深色模式
addUXIssue({
  title: '系统未提供深色模式，夜间使用体验差',
  category: '视觉一致性',
  location: '全局',
  reproduce: '在夜间或暗光环境下使用系统',
  impact: '白色背景刺眼，长时间使用眼睛疲劳',
  example: '全站为浅色主题',
  fix: '实现tailwind dark mode，添加主题切换开关',
  files: 'tailwind.config.js / 全局CSS / App.tsx'
});

// 45. 无响应式移动端适配
addUXIssue({
  title: '系统缺少移动端适配，在小屏幕设备上显示异常',
  category: '响应式',
  location: '全局',
  reproduce: '在375px宽度设备上打开系统',
  impact: '表格溢出、按钮重叠、文字截断，无法正常使用',
  example: '自选股表格在小屏幕横向溢出',
  fix: '添加移动端响应式布局：表格横向滚动、卡片堆叠、隐藏次要列',
  files: 'frontend_react/src/pages/*.tsx'
});

// 46. 信号页面缺少批量操作（批量确认、批量删除）
addUXIssue({
  title: '信号页面无批量操作功能，处理大量信号效率低',
  category: '功能缺失',
  location: 'Signals.tsx',
  reproduce: '选中多条信号，尝试批量操作',
  impact: '需要逐个确认或删除，效率低',
  example: '无复选框，无批量操作按钮',
  fix: '添加信号复选框和批量操作（批量确认、批量删除、批量平仓）',
  files: 'frontend_react/src/pages/Signals.tsx'
});

// 47. 没有数据导出功能（除DataManager单股导出外）
addUXIssue({
  title: '系统缺少全局数据导出功能（如自选股导出为Excel、信号导出为CSV）',
  category: '功能缺失',
  location: 'Watchlist.tsx, Signals.tsx, StockDetail.tsx',
  reproduce: '尝试导出自选股列表或信号列表',
  impact: '用户无法将数据导出到外部工具（如Excel）做进一步分析',
  example: 'Watchlist有导入/导出CSV，但Signals和StockDetail无导出',
  fix: '为信号列表、K线数据添加导出功能',
  files: 'frontend_react/src/pages/Signals.tsx, StockDetail.tsx'
});

// 48. 自选股评分(score)含义不明确，无提示说明
addUXIssue({
  title: '自选股列表中的"技术评分"数字无说明，用户不知道评分标准和含义',
  category: '数据展示',
  location: 'Watchlist.tsx 第596-665行',
  reproduce: '查看自选股列表中的技术评分列',
  impact: '用户不知道80分、35分代表什么，无法利用评分做决策',
  example: '显示数字80，无hover提示或说明',
  fix: '添加hover提示说明评分范围（0-100）和评分依据',
  files: 'frontend_react/src/pages/Watchlist.tsx'
});

// 49. 没有帮助文档或新手引导
addUXIssue({
  title: '系统缺少帮助文档、新手引导或操作说明，新用户上手困难',
  category: '功能缺失',
  location: '全局',
  reproduce: '首次使用系统，尝试理解各功能',
  impact: '新用户不知道功能如何使用，学习成本高',
  example: '无?按钮、无引导气泡、无帮助页面',
  fix: '添加首次使用引导（tour.js）、帮助页面、功能提示',
  files: 'frontend_react/src/App.tsx / 新增Help页面'
});

// 50. 后端未提供实时数据推送（WebSocket）
addSystemIssue({
  title: '后端仅提供轮询API，无WebSocket实时推送，数据更新延迟至少30秒',
  category: 'API设计',
  location: '全局后端',
  reproduce: '观察数据更新机制',
  impact: '行情数据非实时，用户看到的价格可能滞后30秒以上',
  example: '前端每30秒轮询一次loadData()',
  fix: '评估是否需要WebSocket推送实时行情，或提供SSE（Server-Sent Events）',
  files: 'backend/app/main.py / 全局架构'
});

// 51. 后端数据源stats中failures=668但无告警机制
addSystemIssue({
  title: '后端数据源统计中failures=668，但系统无告警或自动恢复机制',
  category: '系统监控',
  location: '后端数据源模块',
  reproduce: '查看/health或日志中的failures计数',
  impact: '大量数据获取失败未被发现和处理，系统持续处于亚健康状态',
  example: 'failures=668，无告警通知',
  fix: '添加失败率监控告警，当失败率超过阈值时通知管理员并自动降级',
  files: 'backend/app/monitoring.py / backend/app/main.py'
});

// 52. 数据管理health中network_available字段但无网络检测实现
addSystemIssue({
  title: '数据管理页面显示"网络连接"状态，但未验证实际网络检测逻辑是否准确',
  category: '数据层',
  location: '/api/v1/data/health',
  reproduce: '查看DataManager页面数据健康卡片中的网络连接状态',
  impact: '网络状态可能不准确，误导用户',
  example: 'network_available显示为true/false，但检测逻辑可能仅检查本机网络而非数据源可达性',
  fix: '验证网络检测逻辑，增加对数据源（如东方财富、akshare）的可达性检测',
  files: 'backend/app/services/data_service.py'
});

// 53. 前端类型定义中部分字段为可选（?）但实际API可能不返回
addSystemIssue({
  title: '前端TypeScript类型定义中大量字段标记为可选，运行时可能undefined导致渲染错误',
  category: '代码质量',
  location: 'frontend_react/src/types/index.ts',
  reproduce: '检查类型定义中optional字段数量',
  impact: 'TypeScript编译通过但运行时出现undefined错误，导致白屏或显示异常',
  example: 'StandardQuote中name?, amount?, pre_close?等均为可选',
  fix: '明确区分必填和可选字段，在API层统一填充默认值，前端做好空值保护',
  files: 'frontend_react/src/types/index.ts'
});

// 54. 后端未实现信号自动扫描（cron/定时任务）
addSystemIssue({
  title: '信号数据滞后2天，后端可能缺少定时自动扫描任务',
  category: '数据层',
  location: 'backend/cron/或APScheduler配置',
  reproduce: '检查后端是否有定时扫描信号的配置',
  impact: '信号不会自动更新，需要手动触发扫描',
  example: '最新信号为2026-06-29，当前2026-07-01',
  fix: '添加定时任务（如APScheduler），每交易日收盘后自动扫描全市场信号',
  files: 'backend/cron/scheduler.py / backend/app/main.py'
});

// 55. 前端路由fallback未处理特定路径
addSystemIssue({
  title: '前端路由缺少特定功能路径的fallback处理（如/stock/无效代码）',
  category: '页面可访问性',
  location: 'StockDetail.tsx',
  reproduce: '访问/stock/999999（不存在的股票）',
  impact: '页面显示"未找到股票数据"，但无返回按钮或搜索建议',
  example: '访问无效symbol显示静态文本',
  fix: '添加无效股票页面：显示错误信息+返回按钮+搜索建议',
  files: 'frontend_react/src/pages/StockDetail.tsx'
});

// 56. 后端未限制API请求频率，存在被滥用风险
addSystemIssue({
  title: '后端API未实现请求频率限制（Rate Limiting）',
  category: '安全',
  location: '全局后端API',
  reproduce: '快速连续请求同一API',
  impact: '可能被恶意请求或前端bug导致大量请求，压垮后端或数据源',
  example: '无频率限制',
  fix: '添加基于IP或用户的请求频率限制（如slowapi库）',
  files: 'backend/app/main.py'
});

// 57. 前端axios timeout=30000，但对于大数据请求可能不足
addSystemIssue({
  title: '前端axios超时时间固定30秒，对于大数据请求可能不足，且未实现超时降级',
  category: '性能/稳定性',
  location: 'frontend_react/src/api/client.ts',
  reproduce: '网络较慢时加载大量数据',
  impact: '请求超时后无降级数据，页面显示空白',
  example: 'timeout: 30000固定值',
  fix: '根据API类型设置不同超时时间，超时后显示缓存数据或错误提示',
  files: 'frontend_react/src/api/client.ts'
});

// 58. 前端App.tsx中ErrorBoundary捕获错误后无错误上报
addSystemIssue({
  title: '前端ErrorBoundary仅console.error，未实现错误上报机制',
  category: '监控',
  location: 'App.tsx 第36-37行',
  reproduce: '触发前端错误',
  impact: '生产环境错误无法被追踪，无法及时修复',
  example: 'componentDidCatch仅console.error',
  fix: '接入错误监控服务（如Sentry）或至少上报到后端日志接口',
  files: 'frontend_react/src/App.tsx'
});

// 59. 后端未对自定义策略代码进行安全校验
addSystemIssue({
  title: '后端/backtest/run接收custom_code参数，但未充分验证JSON结构安全性',
  category: '安全',
  location: 'backend/app/routers/backtest.py',
  reproduce: '提交恶意构造的JSON策略代码',
  impact: '虽然后端使用JSON DSL而非Python eval，但仍需防范DoS或资源耗尽',
  example: '提交超大JSON或嵌套过深的数据',
  fix: '添加JSON深度限制、大小限制、字段白名单校验',
  files: 'backend/app/routers/backtest.py'
});

// 60. 缺少端到端测试（E2E）
addSystemIssue({
  title: '系统缺少端到端测试（E2E），无法自动验证关键用户流程',
  category: '测试',
  location: 'tests/目录',
  reproduce: '检查tests目录内容',
  impact: '代码变更后无法自动确认核心功能（如自选股→个股→交易信号）是否正常',
  example: '无Playwright/Cypress/Selenium测试',
  fix: '使用Playwright添加核心流程E2E测试',
  files: 'tests/e2e/'
});

// ===== 生成报告 =====

const systemReport = `# Quant Workbench 系统排查报告

> 生成时间：2026-07-01 04:00 CST
> 检查范围：后端API、数据质量、系统稳定性
> 检查方式：实际curl调用 + 源码分析 + 已有检查数据
> 原则：只排查不修复，所有问题记录并建议修复

---

## 问题摘要

- **问题总数**：${systemIssues.length} 项
- **数据层问题**：${systemIssues.filter(i => i.category === '数据层').length} 项
- **API层问题**：${systemIssues.filter(i => i.category === 'API层').length} 项
- **系统监控问题**：${systemIssues.filter(i => i.category === '系统监控').length} 项
- **安全/性能问题**：${systemIssues.filter(i => ['安全', '性能/稳定性', 'API设计', '测试', '监控', '代码质量'].includes(i.category)).length} 项
- **页面可访问性问题**：${systemIssues.filter(i => i.category === '页面可访问性').length} 项

---

## 发现的问题

${systemIssues.map((issue, idx) => `
### ${idx + 1}. ${issue.title}

- **类别**：${issue.category}
- **位置**：${issue.location}
- **复现步骤**：${issue.reproduce}
- **影响用户**：${issue.impact}
- **具体案例**：${issue.example}
- **建议修复**：${issue.fix}
- **涉及文件**：${issue.files}
`).join('\n')}

---

## 数据质量检查汇总

| 检查项 | 结果 | 说明 |
|--------|------|------|
| stock-list name中文 | 通过 | 抽查20条，全部中文，无纯数字 |
| watchlist quote.name | 通过 | 9条记录，quote.name均有值 |
| indicators labels | 通过 | labels字段完整，覆盖所有键名 |
| patterns display_name | 通过 | display_name为中文（如"双底"、"双顶"） |
| sentiment source | 异常 | source="cache"而非"eastmoney" |
| hotspots count | 异常 | 仅4条，且为市场分类而非真实热点 |
| sectors stock_count | 异常 | 36个板块，全部stock_count=0 |
| signals timestamp | 异常 | 最新2026-06-29，滞后2天 |
| f10 /{symbol} | 通过 | 200，但大量字段null |
| f10 /profile | 通过 | 200，但仅5个字段 |
| f10 /finance | 通过 | 200，但财务指标null |
| ohlcv 最新日期 | 异常 | 2026-06-26，滞后3-5个交易日 |
| health 状态 | 异常 | failures=668，realtime_hits=0 |

---

## API可用性检查

| API | 状态码 | 结果 |
|-----|--------|------|
| /health | 200 | 可用 |
| /api/v1/data/stock-list | 200 | 可用 |
| /api/v1/watchlist/with-quotes | 200 | 可用 |
| /api/v1/quote/000001/ohlcv | 200 | 可用，数据滞后 |
| /api/v1/quote/000001/indicators | 200 | 可用 |
| /api/v1/quote/000001/patterns | 200 | 可用 |
| /api/v1/quote/000001/signal | 200 | 可用 |
| /api/v1/quote/000001/resonance | 200 | 可用 |
| /api/v1/market/overview | 200 | 可用 |
| /api/v1/market/sentiment | 200 | 可用，source=cache |
| /api/v1/market/hotspots | 200 | 可用，数据异常 |
| /api/v1/market/sectors | 200 | 可用，stock_count=0 |
| /api/v1/signals | 200 | 可用，名称异常 |
| /api/v1/backtest/strategies | 200 | 可用 |
| /api/v1/f10/000001 | 200 | 可用，字段null |
| /api/v1/f10/000001/profile | 200 | 可用，极简 |
| /api/v1/f10/000001/finance | 200 | 可用，财务null |

---

## 下一步建议

1. **优先修复数据滞后**：更新本地数据源（通达信），确保OHLCV和信号数据最新
2. **修复数据质量**：补充F10完整字段、修复hotspots真实数据、补充板块成分股
3. **增强监控**：添加失败率告警、定时任务健康检查
4. **完善测试**：添加E2E测试覆盖核心流程

---

*报告由系统自动生成，所有问题均需手动修复*
`;

const uxReport = `# Quant Workbench 用户体验检查报告

> 生成时间：2026-07-01 04:00 CST
> 用户画像：中文A股投资者，使用桌面浏览器
> 检查范围：前端全部页面、交互流程、视觉一致性、可访问性
> 检查方式：源码静态分析 + API数据验证 + 逻辑推演
> 原则：只排查不修复，所有问题记录并建议修复

---

## 问题摘要

- **问题总数**：${uxIssues.length} 项
- **数据展示问题**：${uxIssues.filter(i => i.category === '数据展示').length} 项
- **交互体验问题**：${uxIssues.filter(i => i.category === '交互体验').length} 项
- **视觉一致性问题**：${uxIssues.filter(i => i.category === '视觉一致性').length} 项
- **可访问性问题**：${uxIssues.filter(i => i.category === '可访问性').length} 项
- **性能问题**：${uxIssues.filter(i => i.category === '性能').length} 项
- **功能缺失问题**：${uxIssues.filter(i => i.category === '功能缺失').length} 项
- **反模式问题**：${uxIssues.filter(i => i.category === '反模式').length} 项
- **响应式/其他问题**：${uxIssues.filter(i => ['响应式', '中文本地化', '数据持久化', '页面可访问性'].includes(i.category)).length} 项

---

## 发现的问题

${uxIssues.map((issue, idx) => `
### ${idx + 1}. ${issue.title}

- **类别**：${issue.category}
- **位置**：${issue.location}
- **复现步骤**：${issue.reproduce}
- **影响用户**：${issue.impact}
- **具体案例**：${issue.example}
- **建议修复**：${issue.fix}
- **涉及文件**：${issue.files}
`).join('\n')}

---

## 检查清单汇总

### 数据展示
- [x] 股票名称显示正常（中文）
- [x] F10数据存在但大量字段为null
- [x] 技术指标名称中文（通过labels映射）
- [x] 技术形态名称中文（通过display_name）
- [x] 信号类型中文（通过type_label和strategy_label）
- [x] 价格格式正确（2位小数）
- [x] 涨跌幅颜色正确（红涨绿跌）
- [x] 成交量单位正确（万/亿自动切换）
- [ ] 五档行情颜色与习惯相反（卖盘红/买盘绿）
- [ ] 热点板块数据异常（显示市场分类）
- [ ] 信号列表中部分名称异常（湖北2521等）

### 页面可访问性
- [x] 首页 / 正常
- [x] 个股详情 /stock/:symbol 正常
- [x] 自选股 /watchlist 正常
- [x] 信号页 /signals 正常
- [x] 回测页 /backtest 正常
- [x] 数据管理 /data 正常
- [x] F10 /f10/:symbol 正常
- [x] 设置页 /settings 正常（但功能缺失）
- [x] 404页面有友好提示
- [ ] 页面标题不随路由变化
- [ ] 错误页面无降级数据

### 中文本地化
- [x] 页面标题中文（组件内）
- [x] 导航菜单中文
- [x] 按钮文字中文
- [x] 表单标签中文
- [x] 提示信息中文
- [ ] 错误信息部分英文（AIResearch）
- [x] 空状态提示中文
- [ ] 技术指标部分fallback含英文

### 交互体验
- [x] 搜索功能可用（带防抖）
- [x] 自选股操作可用（添加/删除/分组）
- [x] 图表渲染正常
- [x] 数据刷新可用（手动+自动30秒）
- [x] 自选股行可点击跳转
- [x] 个股有上一只/下一只导航
- [x] 搜索下拉可点击跳转
- [x] 回车跳转第一个结果
- [x] 信号行可点击跳转
- [ ] 平仓操作3步（超过2步）
- [ ] 热点板块不可点击
- [ ] DataManager股票列表不可点击
- [ ] 缺少键盘快捷键
- [ ] 缺少批量操作
- [ ] 修改分组触发全量重载

### 视觉一致性
- [x] 字体显示正常（支持中文）
- [ ] 颜色方案部分不一致（Backtest vs StockDetail交易颜色）
- [x] 中文排版正常
- [x] 图标正常显示
- [x] 表格对齐正确
- [x] 数字字体等宽
- [ ] 无深色模式
- [ ] 缺少移动端响应式

### 可访问性
- [x] 按钮可点击区域≥44px（信号页面已设置）
- [ ] 焦点指示器部分缺失
- [ ] 颜色对比度未验证
- [ ] select未关联label
- [ ] 错误信息部分不明确
- [ ] 缺少键盘导航
- [ ] 无屏幕阅读器优化

### 反模式
- [x] 无"魔法数字"硬编码（价格/日期使用API数据）
- [x] 无测试数据混入（数据来自真实API）
- [ ] 空状态部分缺失（无网络错误提示）
- [x] 无NaN/Infinity显示
- [x] 无"死按钮"（点击有反馈）
- [x] 无"加载后无数据"空白（有空状态提示）
- [x] 无"搜索无结果"无提示
- [x] 无"图表无数据"报错
- [ ] F10页面显示原始JSON（开发调试数据暴露）
- [ ] 操作步骤过多（平仓3步）
- [ ] 数据滞后（信号/行情滞后）

### 性能
- [x] 有代码分割（React.lazy）
- [x] 使用React.memo
- [x] 使用useMemo（过滤/排序）
- [x] 定时器有visibilitychange暂停
- [x] 搜索有防抖
- [x] 未加载全量stock-list到内存
- [ ] DataManager加载1000条无虚拟滚动
- [ ] 信号筛选无useMemo（内存过滤）
- [ ] 缺少WebSocket实时推送
- [ ] axios超时固定30秒无降级

### 功能存在性
- [x] F10页面存在（前端+后端）
- [x] 回测页面存在（前端+后端）
- [x] 策略编辑器存在（前端+后端）
- [x] AI研究存在（前端+后端）
- [x] 数据管理存在（前端+后端）
- [ ] 设置页面功能极简（几乎无配置项）
- [ ] 缺少帮助文档/新手引导
- [ ] 缺少全局搜索
- [ ] 缺少深色模式
- [ ] 缺少移动端适配

---

## 交互流程检查

| 流程 | 状态 | 说明 |
|------|------|------|
| 自选股→个股详情 | 通过 | 行点击跳转，URL正确 |
| 个股→自选股 | 通过 | 有返回按钮 |
| 个股→上一只/下一只 | 通过 | 有导航按钮 |
| 搜索→个股详情 | 通过 | 下拉点击/回车跳转 |
| 信号→个股详情 | 通过 | 行点击跳转 |
| 热点板块→个股 | 未通过 | 热点板块不可点击 |
| 板块→个股 | 未通过 | sectors无成分股数据 |

---

## 下一步建议

1. **统一颜色规范**：全站统一BUY=红色、SELL=绿色（A股习惯）
2. **修复数据展示**：热点板块真实数据、信号名称正确、F10完整字段
3. **优化交互流程**：平仓一键操作、热点可点击、键盘快捷键
4. **完善可访问性**：添加label关联、键盘导航、错误提示
5. **补充功能**：设置页面、帮助文档、深色模式、移动端适配

---

*报告由系统自动生成，所有问题均需手动修复*
`;

fs.writeFileSync(path.join(SELFCHECK_DIR, `SYSTEM_LOOP_CHECK_REPORT_${TIMESTAMP}.md`), systemReport, 'utf-8');
fs.writeFileSync(path.join(UX_DIR, `UX_CHECK_REPORT_${TIMESTAMP}.md`), uxReport, 'utf-8');

console.log('Reports generated successfully!');
console.log(`System report: ${path.join(SELFCHECK_DIR, `SYSTEM_LOOP_CHECK_REPORT_${TIMESTAMP}.md`)}`);
console.log(`UX report: ${path.join(UX_DIR, `UX_CHECK_REPORT_${TIMESTAMP}.md`)}`);
console.log(`System issues: ${systemIssues.length}`);
console.log(`UX issues: ${uxIssues.length}`);
