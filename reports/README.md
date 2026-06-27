# Quant Workbench 报告目录说明

## 目录结构

```
a_share_system/
├── reports/
│   ├── selfcheck/          # 系统状态排查报告（每小时整点）
│   │   ├── SYSTEM_LOOP_CHECK_REPORT_YYYY-MM-DD_HHMM.md
│   │   ├── SELF_CHECK_REPORT_YYYYMMDD_EXECUTED.md
│   │   └── ...
│   ├── ux/                 # 用户体验检查报告（每小时整点）
│   │   ├── UX_CHECK_REPORT_YYYY-MM-DD_HHMM.md
│   │   └── ...
│   ├── postmarket/         # 盘后分析报告（保留但当前未使用）
│   │   └── ...
│   └── README.md           # 本文件
```

## 报告类型

### 1. selfcheck/ - 系统状态排查报告
**生成频率**: 每小时整点执行一次  
**内容**: 
- 后端存活状态
- API 可用性检查（11个核心接口）
- 数据真实性验证
- 数据时效性检查
- 前端构建状态
- 问题汇总（只记录，不修复）

**文件命名**: `SYSTEM_LOOP_CHECK_REPORT_YYYY-MM-DD_HHMM.md`

### 2. ux/ - 用户体验检查报告
**生成频率**: 每小时整点执行一次（与系统排查同时）
**内容**:
- 数据展示检查（F10乱码、股票名称显示、技术指标翻译）
- 页面可访问性（打不开、白屏、404/500）
- 中文本地化（英文未翻译、技术术语对照）
- 交互体验（按钮、搜索、图表、数据刷新）
- 视觉一致性（字体、排版、颜色、图标）

**文件命名**: `UX_CHECK_REPORT_YYYY-MM-DD_HHMM.md`

**技术术语检查项**（示例）:
| 英文 | 正确中文 | 检查位置 |
|------|---------|---------|
| Head and Shoulders | 头肩顶 | 型态识别 |
| Breakout | 突破 | 信号页面 |
| Divergence | 背离 | 指标分析 |
| Overbought | 超买 | RSI指标 |
| Bullish | 看多 | 信号页面 |

### 3. postmarket/ - 盘后分析报告
**当前状态**: 已停用（盘后流水线任务已删除）
**保留原因**: 目录保留，如需恢复盘后任务可直接使用

## VSCode 使用建议

1. **打开工作区**: 在 VSCode 中打开 `a_share_system` 文件夹
2. **查看报告**: 直接浏览 `reports/` 目录
3. **搜索历史**: 使用 VSCode 搜索功能查找关键词
4. **对比分析**: 使用 Git 或文件对比查看变化趋势

## 注意事项

- 报告只记录状态，不自动修复问题
- 发现问题需手动处理
- 报告保留历史，可回溯系统状态变化
