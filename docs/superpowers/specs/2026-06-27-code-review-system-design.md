# 三层代码审查体系设计文档

**日期：** 2026-06-27  
**主题：** CodeRabbit + Claude Code Review + 人类 Reviewer 三层代码审查体系  
**适用范围：** 当前项目（Quant Workbench）及后续项目复用

---

## 1. 背景与目标

当前项目为 FastAPI + React 的量化工作台，目前：
- 尚未纳入 Git 版本管理
- 无 CI/CD
- 无自动化代码审查
- 测试覆盖为 0%

本设计旨在建立一套可持续运转的三层代码审查体系，实现：
- **CodeRabbit**：每 PR 自动筛查，过滤风格、常见 bug、安全模式问题
- **Claude Code Review**：对核心业务逻辑、大型重构、安全敏感改动做深度多智能体审查
- **人类 reviewer**：聚焦架构与业务逻辑，判断“应不应该这样设计”

---

## 2. 总体架构

```text
┌─────────────────────────────────────────────────────────────┐
│                        GitHub Pull Request                   │
└──────────────┬──────────────────────────────┬───────────────┘
               │                              │
               ▼                              ▼
    ┌─────────────────────┐      ┌──────────────────────────┐
    │  CodeRabbit         │      │  deep-review 标签         │
    │  （每 PR 自动触发）   │      │  （人工/自动标记）         │
    │                     │      └──────────┬───────────────┘
    │  过滤：风格、常见 bug │                 │
    │  安全模式、低价值噪音 │                 ▼
    │                     │      ┌──────────────────────────┐
    └──────────┬──────────┘      │  GitHub Actions          │
               │                 │  调用 Claude Code Review │
               │                 │  多智能体深度审查         │
               │                 └──────────┬───────────────┘
               │                            │
               ▼                            ▼
    ┌─────────────────────┐      ┌──────────────────────────┐
    │  门禁：必须通过       │      │  输出：分级报告           │
    │  否则阻塞合并         │      │  阻塞项必须解决           │
    └─────────────────────┘      └──────────────────────────┘
               │                            │
               └──────────────┬─────────────┘
                              ▼
              ┌───────────────────────────────┐
              │  人类 reviewer                 │
              │  聚焦架构与业务逻辑             │
              │  批准后可合并                   │
              └───────────────────────────────┘
```

---

## 3. 分阶段落地计划

### 3.1 第一阶段：最小可用版（方案 A，半天内）

**目标：** 先让 CodeRabbit 跑起来，Claude Code Review 可手动触发。

1. 初始化 Git 仓库，推送到 GitHub 私有仓库。
2. 安装并启用 CodeRabbit GitHub App。
3. 创建基础 PR 模板，含 `deep-review` 标签勾选框。
4. 配置分支保护：CodeRabbit 检查通过 + 1 名人类 reviewer 批准后才能合并。
5. 对带 `deep-review` 标签的 PR，在本地或自托管 Runner 上手动运行 Claude Code Review，结果贴到 PR 评论。

### 3.2 第二阶段：完整自动化（方案 B，1-2 天）

**目标：** 把 Claude Code Review 也纳入自动化门禁。

1. 编写 `.coderabbit.yaml`，定制 Python/React 规则。
2. 创建 GitHub Actions 工作流：
   - 监听 `labeled` 事件（标签为 `deep-review`）。
   - 在自托管 Runner 上调用 Claude Code CLI 进行多智能体深度审查。
   - 在 PR 中发布结构化报告，并设置 Check Run 状态。
3. 分支保护增加 Claude Code 阻塞项检查。
4. 可选：根据改动路径自动建议/添加 `deep-review` 标签。

---

## 4. GitHub 仓库与分支保护设计

### 4.1 仓库初始化

```bash
git init
git add .
git commit -m "init: 初始化 Quant Workbench"
git branch -M main
git remote add origin https://github.com/<your-org>/a_share_system.git
git push -u origin main
```

### 4.2 分支保护规则（针对 `main`）

| 规则 | 说明 |
|------|------|
| 需要 PR 才能合并 | 禁止直接 push 到 main |
| 至少 1 名人类 reviewer 批准 | 人类 reviewer 保留最终决策权 |
| CodeRabbit 检查通过 | 自动触发，阻塞合并 |
| Claude Code 检查通过 | 仅对带 `deep-review` 标签的 PR 生效 |
| 解决所有对话后才能合并 | 防止未处理的 AI 评论被忽略 |

### 4.3 PR 模板

文件路径：`.github/pull_request_template.md`

```markdown
## 改动说明

## 影响范围

- [ ] 核心业务逻辑（信号/回测/数据引擎）
- [ ] 大型重构（>300 行或影响多个模块）
- [ ] 安全敏感改动（认证、配置、依赖升级）
- [ ] 仅 UI / 工具函数 / 文档

## 审查标签

维护者请根据上方勾选情况添加标签：
- `deep-review`：涉及核心逻辑/安全/大型重构，需要 Claude Code 深度审查
- `bugfix` / `feature` / `docs`：常规分类标签

## 自查清单

- [ ] 本地测试通过 或 happy path 已验证
- [ ] 没有引入新的 print 调试语句
- [ ] 未提交 data/raw/tmp/ 等临时文件
```

### 4.4 标签策略

| 标签 | 用途 | 触发行为 |
|------|------|----------|
| `deep-review` | 需要 Claude Code 深度审查 | 触发 GitHub Actions 深度审查 |
| `coderabbit-ignore` | 特殊情况跳过 CodeRabbit | 需人类 reviewer 同意 |
| `security` | 安全相关 | 自动建议打 `deep-review` |
| `refactor` | 重构 | 自动建议打 `deep-review` |

---

## 5. CodeRabbit 配置

文件路径：`.coderabbit.yaml`

```yaml
language: "zh-CN"

reviews:
  profile: "chill"
  request_changes_workflow: true
  high_level_summary: true
  poem: false
  review_status: true
  collapse_walkthrough: true

  path_filters:
    - "!data/raw/**"
    - "!data/raw/tmp/**"
    - "!frontend_react/node_modules/**"
    - "!frontend_react/dist/**"
    - "!**/__pycache__/**"
    - "!frontend_react/package-lock.json"

  path_instructions:
    - path: "backend/**/*.py"
      instructions: |
        关注 FastAPI 路由参数校验、Pydantic 模型、SQL 注入风险、异常处理。
        检查是否有未验证的用户输入直接拼接到 SQL 或文件路径。
    - path: "frontend_react/src/**/*.tsx"
      instructions: |
        关注 React Hook 依赖、潜在内存泄漏、TypeScript 类型安全、UI 状态管理。
    - path: "core/**/*.py"
      instructions: |
        这是系统核心模块，关注算法正确性、边界条件、性能热点、数据契约。
    - path: "strategy/**/*.py"
      instructions: |
        这是交易策略模块，关注信号计算逻辑、止损条件、滑点/手续费假设是否合理。

  auto_review:
    enabled: true
    drafts: false
    base_branches: ["main"]

  chat:
    auto_reply: true
```

---

## 6. Claude Code Review 工作流（自托管 Runner）

### 6.1 触发条件

- PR 被打上 `deep-review` 标签时触发。
- 重新打标签或推送到已标记 PR 时重新触发。

### 6.2 工作流文件

文件路径：`.github/workflows/claude-code-review.yml`

```yaml
name: Claude Code Deep Review

on:
  pull_request:
    types: [labeled, synchronize]

jobs:
  deep-review:
    if: contains(github.event.pull_request.labels.*.name, 'deep-review')
    runs-on: self-hosted
    steps:
      - name: 检出 PR 代码
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: 准备审查上下文
        id: context
        run: |
          git fetch origin ${{ github.event.pull_request.base.ref }}
          git diff origin/${{ github.event.pull_request.base.ref }} > pr_diff.patch
          echo "pr_number=${{ github.event.pull_request.number }}" >> $GITHUB_OUTPUT
          echo "base_ref=${{ github.event.pull_request.base.ref }}" >> $GITHUB_OUTPUT
          echo "head_sha=${{ github.event.pull_request.head.sha }}" >> $GITHUB_OUTPUT

      - name: 运行 Claude Code 深度审查
        env:
          CLAUDE_CODE_REVIEW_PROMPT: .github/review_prompts/deep_review.md
        run: |
          claude code --dangerously-sandbox \
            --allow-tools "Read,Edit,Bash,Grep" \
            --message "请按照 ${CLAUDE_CODE_REVIEW_PROMPT} 审查本次 PR，输入文件为 pr_diff.patch，输出为 JSON 格式的审查报告" \
            > claude_review_report.json

      - name: 解析并发布审查报告
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            const report = JSON.parse(fs.readFileSync('claude_review_report.json', 'utf8'));
            // 生成 PR 评论和 Check Run 状态
            // 实现细节（评论格式化、Check Run 结论判断）在实现计划中细化
```

### 6.3 本地手动触发方式（备选）

```bash
# 1. 在 PR 分支执行
gh pr checkout <PR_NUMBER>

# 2. 生成 diff
git diff origin/main > pr_diff.patch

# 3. 调用 Claude Code 审查
claude code --message "请按 .github/review_prompts/deep_review.md 审查 pr_diff.patch"

# 4. 把结果贴回 PR 评论
```

---

## 7. Claude Code 审查提示词

文件路径：`.github/review_prompts/deep_review.md`

```markdown
你是一名严格的代码审查专家。请审查以下 PR diff，重点关注：

1. 核心业务逻辑错误（信号计算、回测、数据处理）
2. 安全漏洞（注入、越权、敏感信息泄露、依赖漏洞）
3. 性能问题（循环、IO、内存泄漏）
4. 并发与状态管理问题
5. 大型重构的兼容性与回滚风险

输出格式要求（必须严格按 JSON）：

```json
{
  "summary": "整体评价，1-2句话",
  "severity": "blocking|warning|info",
  "findings": [
    {
      "file": "backend/services/signal_engine.py",
      "line": 42,
      "severity": "blocking",
      "category": "logic|security|performance|architecture",
      "description": "问题描述",
      "suggestion": "修复建议"
    }
  ],
  "action_required": ["blocking 项必须解决后才能合并"]
}
```

注意：
- 不要评论代码风格问题（由 CodeRabbit 处理）。
- 不确定时标注为 warning，不要过度阻断。
```

---

## 8. 审查报告格式与门禁规则

### 8.1 报告发布形式

- **PR 评论**：人类 reviewer 可读，按严重程度分组。
- **Check Run**：GitHub 可据此设置分支保护门禁。

### 8.2 评论模板示例

```markdown
## 🤖 Claude Code 深度审查报告

**PR:** #123
**审查范围:** 核心业务逻辑 / 安全 / 大型重构
**整体评级:** ⚠️ 需要修改

### 🚫 阻塞项（必须解决）

| 文件 | 位置 | 问题 | 建议 |
|------|------|------|------|
| `backend/services/backtest_engine.py` | L145 | 止损条件使用 `<` 而不是 `<=`，可能导致边界漏判 | 统一使用 `<=` 并补充边界测试 |
| `core/parallel_engine.py` | L88 | 进程池未设置 `max_workers` 上限，可能耗尽系统资源 | 根据 CPU 核心数限制 |

### ⚠️ 警告项（建议处理）

| 文件 | 位置 | 问题 | 建议 |
|------|------|------|------|
| `frontend_react/src/stores/signalStore.ts` | L34 | `useEffect` 依赖数组缺失，可能导致重复请求 | 补充依赖或拆分子逻辑 |

### ℹ️ 建议项（可选）

- `data/download_daily.py` 的日志可以更结构化，便于后续可观测性改造。

**处理要求：** 阻塞项必须全部解决或经人类 reviewer 显式同意忽略后，才能合并。
```

### 8.3 门禁规则汇总

| 层级 | 触发条件 | 阻塞合并？ | 失败处理 |
|------|----------|------------|----------|
| CodeRabbit | 每 PR 自动 | 是 | 修复问题或申请忽略 |
| Claude Code | `deep-review` 标签 | 阻塞项必须解决 | 修复或人类 reviewer 批准忽略 |
| 人类 reviewer | 每 PR | 是 | 架构/业务判断 |

---

## 9. 错误处理与回退策略

| 场景 | 处理策略 |
|------|----------|
| CodeRabbit 服务不可用 | 临时禁用其门禁，改为人类 reviewer 加强审查；恢复后重新启用。 |
| Claude Code CLI 在 Runner 上运行失败 | Actions 标记为 `neutral` 或 `failure`，并提示维护者手动在本地跑审查。 |
| Claude Code 输出格式损坏 | Actions 捕获异常，发布原始输出到 PR，由人类 reviewer 判断。 |
| PR 被误标 `deep-review` | 移除标签即可取消审查；标签重新添加后再次触发。 |
| 自托管 Runner 离线 | 工作流进入队列；超时后提醒维护者检查 Runner 状态或转本地审查。 |

---

## 10. 落地验证清单

### 10.1 第一阶段验证（方案 A）

- [ ] 项目成功推送到 GitHub 私有仓库。
- [ ] CodeRabbit 在测试 PR 上自动发表评论。
- [ ] 分支保护阻止未通过 CodeRabbit 的 PR 合并。
- [ ] 人类 reviewer 能手动对带 `deep-review` 标签的 PR 运行 Claude Code。

### 10.2 第二阶段验证（方案 B）

- [ ] 给 PR 打 `deep-review` 标签后，Actions 自动触发。
- [ ] Claude Code 输出结构化 JSON 报告。
- [ ] 阻塞项未解决时，PR 无法合并。
- [ ] 常规 PR（无 `deep-review` 标签）不触发深度审查，避免浪费 token。

---

## 11. 未来项目复用模板

当前项目跑通后，把以下内容整理成复用包：

```text
.github/templates/
├── coderabbit.yaml.template
├── workflows/
│   └── claude-code-review.yml.template
├── pull_request_template.md
└── review_prompts/
    └── deep_review.md

docs/
└── review-setup/
    └── README.md          # 新项目接入指南
```

新项目接入步骤：
1. 复制 `.github/templates/` 到项目根目录。
2. 在 GitHub 安装 CodeRabbit App。
3. 配置自托管 Runner 或启用本地审查流程。
4. 根据项目技术栈微调 `.coderabbit.yaml` 的路径指令。

---

## 12. 决策记录

| 决策项 | 选择 | 理由 |
|--------|------|------|
| Git 托管平台 | GitHub 私有仓库 | CodeRabbit 原生支持最好，Actions 生态最成熟 |
| Claude Code 触发方式 | `deep-review` 标签 | 人工判断兜底，避免所有 PR 都跑高成本深度审查 |
| Claude Code 实现方式 | 自托管 Runner 上运行 Claude Code CLI | 数据不出境，复用已有额度，上下文理解更好 |
| 结果处理 | CodeRabbit 必过，Claude Code 阻塞项必解决 | 既保证质量，又不过度增加合并成本 |
| 落地节奏 | 方案 A → 方案 B | 先最小闭环，再完整自动化 |

---

## 13. 待后续细化

- [ ] 自托管 Runner 的具体机器配置与 Claude Code CLI 登录方式。
- [ ] CodeRabbit 免费额度用尽后的付费或降级策略。
- [ ] 是否引入自动标签建议 Actions（根据改动路径自动推荐 `deep-review`）。
- [ ] 多项目复用模板是否独立为单独仓库。
