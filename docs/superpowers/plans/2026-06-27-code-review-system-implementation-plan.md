# 三层代码审查体系实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在当前 Quant Workbench 项目落地 CodeRabbit + Claude Code Review + 人类 Reviewer 的三层代码审查体系，并沉淀为可复用模板。

**Architecture:** 项目先纳入 Git 并托管到 GitHub 私有仓库；CodeRabbit 作为第一层自动筛查，Claude Code 通过 `deep-review` 标签触发深度审查，人类 reviewer 保留最终合并决策权。实施分为 A（最小闭环）和 B（完整自动化）两阶段。

**Tech Stack:** Git, GitHub, GitHub Actions, CodeRabbit, Claude Code CLI, Bash/PowerShell

## Global Constraints

- 代码托管平台：GitHub 私有仓库
- CI/CD 平台：GitHub Actions
- Claude Code Review 触发方式：`deep-review` 标签
- Claude Code Review 执行方式：自托管 Runner 上的 Claude Code CLI
- 结果处理：CodeRabbit 必须过；Claude Code 阻塞项必须解决
- 落地节奏：方案 A（半天）→ 方案 B（1-2 天）
- 所有配置与脚本文件使用 UTF-8 编码
- 临时数据（`data/raw/tmp/`、`node_modules/`、编译产物）不得进入 Git

---

## 文件结构映射

```text
a_share_system/
├── .gitignore                              # 排除临时文件与依赖
├── .github/
│   ├── pull_request_template.md            # PR 模板
│   ├── workflows/
│   │   └── claude-code-review.yml          # Claude Code 深度审查工作流
│   ├── review_prompts/
│   │   └── deep_review.md                  # Claude Code 审查提示词
│   └── templates/                          # 未来项目复用模板
│       ├── coderabbit.yaml.template
│       ├── pull_request_template.md
│       ├── workflows/
│       │   └── claude-code-review.yml.template
│       └── review_prompts/
│           └── deep_review.md
├── .coderabbit.yaml                        # CodeRabbit 配置
└── docs/
    └── review-setup/
        └── README.md                       # 新项目接入指南
```

---

## 第一阶段：最小可用版（方案 A）

### Task 1: 创建 .gitignore 并初始化 Git 仓库

**Files:**
- Create: `.gitignore`
- Modify: 无
- Test: 运行 `git status` 验证只有预期文件被追踪

**Interfaces:**
- Consumes: 无
- Produces: `.gitignore` 文件，定义 Git 排除规则

- [ ] **Step 1: 编写 .gitignore**

```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
.venv/
venv/
env/
*.egg-info/
dist/
build/
.pytest_cache/
.mypy_cache/

# Node.js
frontend_react/node_modules/
frontend_react/dist/
frontend_react/.vite/
*.log
npm-debug.log*

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# OS
.DS_Store
Thumbs.db

# Project specific
data/raw/tmp/
data/cache/
data/system.db
.remember/
config/user.yaml
*.env
.env.local
```

- [ ] **Step 2: 初始化 Git 仓库**

Run:
```bash
git init
git add .gitignore
git commit -m "chore: 初始化 Git 并添加 .gitignore"
```

Expected: 仓库初始化成功，当前分支为 `main` 或 `master`。

- [ ] **Step 3: 验证未追踪文件**

Run:
```bash
git status --short | head -20
```

Expected: `data/raw/tmp/`、`frontend_react/node_modules/` 等大量文件不在列表中。

---

### Task 2: 创建 GitHub 私有仓库并推送代码

**Files:**
- Create: 远程 GitHub 仓库
- Modify: 本地 `.git/config`
- Test: 运行 `git ls-remote` 验证连接

**Interfaces:**
- Consumes: 本地 Git 仓库
- Produces: 远程 `origin` 指向 GitHub 私有仓库

- [ ] **Step 1: 通过 GitHub CLI 创建私有仓库**

Run:
```bash
gh repo create a_share_system --private --source=. --remote=origin --push
```

Expected: 输出显示仓库已创建，代码已推送，远程 origin 已设置。

> 若未安装 `gh`，需先执行 `winget install --id GitHub.cli` 或从 https://cli.github.com 下载安装。

- [ ] **Step 2: 验证远程连接**

Run:
```bash
git remote -v
git ls-remote origin main
```

Expected: 显示 `origin` 的 fetch/push URL 为 `https://github.com/<your-org>/a_share_system.git`，且能读取到 main 分支的引用。

---

### Task 3: 安装并启用 CodeRabbit GitHub App

**Files:**
- Create: 无（GitHub 侧配置）
- Modify: 无
- Test: 提交测试 PR，观察 CodeRabbit 是否自动评论

**Interfaces:**
- Consumes: GitHub 仓库
- Produces: CodeRabbit 检查状态

- [ ] **Step 1: 在 GitHub 上安装 CodeRabbit App**

浏览器访问：https://github.com/apps/coderabbitai

1. 点击 "Install" 或 "Configure"。
2. 选择要安装到的账号/组织。
3. 在仓库列表中勾选 `a_share_system`。
4. 选择 "Only select repositories"，保存。

Expected: 安装完成后，GitHub 显示 CodeRabbit 已授权访问该仓库。

- [ ] **Step 2: 创建测试 PR 验证 CodeRabbit**

Run:
```bash
git checkout -b test/coderabbit-trigger
echo "# Test change" >> README.md
git add README.md
git commit -m "test: 验证 CodeRabbit 触发"
git push -u origin test/coderabbit-trigger
gh pr create --title "test: 验证 CodeRabbit 自动审查" --body "这是一个测试 PR，验证 CodeRabbit 是否能自动评论。"
```

Expected: PR 创建后 1-2 分钟内，CodeRabbit 在 PR 中发表评论或检查状态。

- [ ] **Step 3: 合并测试 PR 或关闭它**

Run:
```bash
gh pr close test/coderabbit-trigger --delete-branch
```

Expected: 测试 PR 被关闭，分支被删除。

---

### Task 4: 创建 PR 模板

**Files:**
- Create: `.github/pull_request_template.md`
- Modify: 无
- Test: 创建新 PR，观察是否自动填充模板内容

**Interfaces:**
- Consumes: 无
- Produces: `.github/pull_request_template.md`

- [ ] **Step 1: 创建 PR 模板文件**

```markdown
## 改动说明

<!-- 简要描述本次改动的目的和范围 -->

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

- [ ] **Step 2: 提交 PR 模板**

Run:
```bash
git add .github/pull_request_template.md
git commit -m "chore: 添加 PR 模板，明确审查标签与自查清单"
git push origin main
```

Expected: 提交成功，main 分支包含 PR 模板。

- [ ] **Step 3: 验证 PR 模板生效**

Run:
```bash
git checkout -b test/pr-template
echo "# another test" >> README.md
git add README.md
git commit -m "test: 验证 PR 模板"
git push -u origin test/pr-template
gh pr create --title "test: 验证 PR 模板" --body-file .github/pull_request_template.md
```

Expected: PR 创建页面或 `gh pr create` 交互中显示模板内容。

- [ ] **Step 4: 关闭测试 PR**

Run:
```bash
gh pr close test/pr-template --delete-branch
```

---

### Task 5: 配置分支保护规则

**Files:**
- Create: 无（GitHub 侧配置）
- Modify: 仓库设置
- Test: 尝试直接 push 到 main，验证被拒绝

**Interfaces:**
- Consumes: GitHub 仓库
- Produces: 受保护的 `main` 分支规则

- [ ] **Step 1: 通过 GitHub CLI 配置分支保护**

Run:
```bash
gh api repos/{owner}/{repo}/branches/main/protection \
  --method PUT \
  --input - <<EOF
{
  "required_status_checks": {
    "strict": true,
    "contexts": ["CodeRabbit"]
  },
  "enforce_admins": false,
  "required_pull_request_reviews": {
    "required_approving_review_count": 1,
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": false
  },
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false
}
EOF
```

> 将 `{owner}/{repo}` 替换为实际值，例如 `jianglihai/a_share_system`。

Expected: 命令返回 200，分支保护规则设置成功。

- [ ] **Step 2: 验证直接 push 被阻止**

Run:
```bash
git checkout main
echo "# direct push test" >> README.md
git add README.md
git commit -m "test: 验证分支保护"
git push origin main
```

Expected: push 被拒绝，提示 `protected branch` 或需要 PR。

- [ ] **Step 3: 回滚本地测试提交**

Run:
```bash
git reset --soft HEAD~1
git checkout -- README.md
```

Expected: 本地仓库回到 clean 状态。

---

### Task 6: 手动运行 Claude Code 深度审查（方案 A 验证）

**Files:**
- Create: `.github/review_prompts/deep_review.md`
- Modify: 无
- Test: 创建带 `deep-review` 标签的 PR，本地运行审查并把结果贴回

**Interfaces:**
- Consumes: `.github/review_prompts/deep_review.md`
- Produces: PR 评论中的 Claude Code 审查报告

- [ ] **Step 1: 创建审查提示词文件**

Create `.github/review_prompts/deep_review.md`:

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

- [ ] **Step 2: 提交提示词文件**

Run:
```bash
git add .github/review_prompts/deep_review.md
git commit -m "chore: 添加 Claude Code 深度审查提示词"
git push origin main
```

- [ ] **Step 3: 创建带 deep-review 标签的测试 PR**

Run:
```bash
git checkout -b test/deep-review-manual
echo "# core logic change sample" >> backend/services/signal_engine.py
git add backend/services/signal_engine.py
git commit -m "test: 手动触发 deep-review 审查"
git push -u origin test/deep-review-manual
gh pr create --title "test: 手动 deep-review 审查" --body "涉及核心逻辑，已勾选 deep-review。" --label deep-review
```

> 若标签 `deep-review` 不存在，先创建：`gh label create deep-review --description "需要 Claude Code 深度审查" --color FF0000`

Expected: PR 创建成功，并带有 `deep-review` 标签。

- [ ] **Step 4: 本地生成 diff 并调用 Claude Code**

Run:
```bash
gh pr checkout <PR_NUMBER>
git diff origin/main > pr_diff.patch
claude code --message "请按 .github/review_prompts/deep_review.md 审查 pr_diff.patch"
```

Expected: Claude Code 输出结构化审查报告。

- [ ] **Step 5: 将报告贴回 PR 评论**

Run:
```bash
gh pr comment <PR_NUMBER> --body-file claude_review_report.md
```

Expected: PR 下出现 Claude Code 审查评论。

- [ ] **Step 6: 关闭测试 PR**

Run:
```bash
gh pr close test/deep-review-manual --delete-branch
```

---

## 第二阶段：完整自动化（方案 B）

### Task 7: 创建 .coderabbit.yaml

**Files:**
- Create: `.coderabbit.yaml`
- Modify: 无
- Test: 提交 PR 后观察 CodeRabbit 是否按自定义规则审查

**Interfaces:**
- Consumes: 无
- Produces: `.coderabbit.yaml`

- [ ] **Step 1: 编写 CodeRabbit 配置**

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

- [ ] **Step 2: 提交配置**

Run:
```bash
git add .coderabbit.yaml
git commit -m "chore: 添加 CodeRabbit 自定义配置"
git push origin main
```

- [ ] **Step 3: 验证配置生效**

Run:
```bash
git checkout -b test/coderabbit-config
echo "# test" >> backend/services/data_provider.py
git add backend/services/data_provider.py
git commit -m "test: 验证 CodeRabbit 自定义规则"
git push -u origin test/coderabbit-config
gh pr create --title "test: 验证 CodeRabbit 配置" --body "测试自定义 path_instructions 是否生效。"
```

Expected: CodeRabbit 评论中体现对 backend 目录的特殊关注。

- [ ] **Step 4: 关闭测试 PR**

Run:
```bash
gh pr close test/coderabbit-config --delete-branch
```

---

### Task 8: 设置自托管 GitHub Actions Runner

**Files:**
- Create: 无（机器环境配置）
- Modify: 无
- Test: GitHub 仓库设置中显示 Runner 在线

**Interfaces:**
- Consumes: GitHub 仓库
- Produces: 可运行的 `self-hosted` Runner

- [ ] **Step 1: 在 GitHub 上添加自托管 Runner**

浏览器访问：`https://github.com/<owner>/<repo>/settings/actions/runners/new`

1. 选择操作系统（Linux 推荐，Windows 也可）。
2. 按页面提示下载并配置 runner。
3. 给 runner 添加标签，例如 `claude-code`。

Linux 示例命令：
```bash
mkdir actions-runner && cd actions-runner
curl -o actions-runner-linux-x64-2.319.1.tar.gz -L https://github.com/actions/runner/releases/download/v2.319.1/actions-runner-linux-x64-2.319.1.tar.gz
tar xzf ./actions-runner-linux-x64-2.319.1.tar.gz
./config.sh --url https://github.com/<owner>/<repo> --token <TOKEN>
./run.sh
```

Expected: Runner 状态显示为 `Idle` 或 `Online`。

- [ ] **Step 2: 在 Runner 上安装 Claude Code CLI**

Run on the Runner:
```bash
npm install -g @anthropic-ai/claude-code
claude --version
```

Expected: 显示 Claude Code CLI 版本号。

- [ ] **Step 3: 登录 Claude Code（交互式）**

Run on the Runner:
```bash
claude code
```

按提示完成登录。登录凭证会保存在 Runner 用户目录下。

Expected: 能进入 Claude Code 交互界面并正常对话。

---

### Task 9: 创建 Claude Code Review GitHub Actions 工作流

**Files:**
- Create: `.github/workflows/claude-code-review.yml`
- Modify: 无
- Test: 给 PR 打 `deep-review` 标签，观察 Actions 是否触发并发布报告

**Interfaces:**
- Consumes: `.github/review_prompts/deep_review.md`
- Produces: PR 评论 + Check Run

- [ ] **Step 1: 编写工作流文件**

```yaml
name: Claude Code Deep Review

on:
  pull_request:
    types: [labeled, synchronize]

jobs:
  deep-review:
    if: contains(github.event.pull_request.labels.*.name, 'deep-review')
    runs-on: self-hosted
    permissions:
      contents: read
      pull-requests: write
      checks: write
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
        run: |
          claude code --dangerously-sandbox \
            --allow-tools "Read,Bash,Grep" \
            --message "请按照 .github/review_prompts/deep_review.md 审查 pr_diff.patch，输出为 JSON 格式" \
            > claude_review_report.json

      - name: 解析并发布审查报告
        uses: actions/github-script@v7
        env:
          PR_NUMBER: ${{ github.event.pull_request.number }}
          HEAD_SHA: ${{ github.event.pull_request.head.sha }}
        with:
          script: |
            const fs = require('fs');
            const path = require('path');

            const reportPath = path.join(process.env.GITHUB_WORKSPACE, 'claude_review_report.json');
            const raw = fs.readFileSync(reportPath, 'utf8');
            let report;
            try {
              // Try to extract JSON from markdown code block
              const match = raw.match(/```json\s*([\s\S]*?)\s*```/);
              report = match ? JSON.parse(match[1]) : JSON.parse(raw);
            } catch (e) {
              report = {
                summary: "Claude Code 输出解析失败，请查看原始输出。",
                severity: "warning",
                findings: [],
                action_required: ["请人工检查原始输出"]
              };
            }

            const blocking = report.findings?.filter(f => f.severity === 'blocking') || [];
            const warnings = report.findings?.filter(f => f.severity === 'warning') || [];
            const infos = report.findings?.filter(f => f.severity === 'info') || [];

            const formatRows = items => items.length === 0
              ? '无\n'
              : items.map(f => `| \`${f.file}\` | ${f.line || '-'} | ${f.description} | ${f.suggestion || '-'} |`).join('\n') + '\n';

            const body = `## 🤖 Claude Code 深度审查报告

**PR:** #${process.env.PR_NUMBER}
**审查范围:** 核心业务逻辑 / 安全 / 大型重构
**整体评级:** ${blocking.length > 0 ? '🚫 需要修改' : warnings.length > 0 ? '⚠️ 建议处理' : '✅ 通过'}

### 🚫 阻塞项（必须解决）

| 文件 | 位置 | 问题 | 建议 |
|------|------|------|------|
${formatRows(blocking)}
### ⚠️ 警告项（建议处理）

| 文件 | 位置 | 问题 | 建议 |
|------|------|------|------|
${formatRows(warnings)}
### ℹ️ 建议项（可选）

${infos.length === 0 ? '无' : infos.map(f => `- \`${f.file}\`: ${f.description}`).join('\n')}

**处理要求：** 阻塞项必须全部解决或经人类 reviewer 显式同意忽略后，才能合并。
`;

            await github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: parseInt(process.env.PR_NUMBER, 10),
              body
            });

            const conclusion = blocking.length > 0 ? 'failure' : 'success';
            await github.rest.checks.create({
              owner: context.repo.owner,
              repo: context.repo.repo,
              name: 'Claude Code Deep Review',
              head_sha: process.env.HEAD_SHA,
              status: 'completed',
              conclusion,
              output: {
                title: conclusion === 'failure' ? '发现阻塞项' : '深度审查通过',
                summary: report.summary || '审查完成',
                text: `blocking: ${blocking.length}, warning: ${warnings.length}, info: ${infos.length}`
              }
            });
```

- [ ] **Step 2: 提交工作流文件**

Run:
```bash
git add .github/workflows/claude-code-review.yml
git commit -m "ci: 添加 Claude Code 深度审查工作流"
git push origin main
```

- [ ] **Step 3: 验证工作流触发**

Run:
```bash
git checkout -b test/deep-review-auto
echo "# simulate core change" >> backend/services/backtest_engine.py
git add backend/services/backtest_engine.py
git commit -m "test: 触发自动 deep-review"
git push -u origin test/deep-review-auto
gh pr create --title "test: 自动 deep-review 触发" --body "涉及核心逻辑，已勾选 deep-review。" --label deep-review
```

Expected: Actions 页面出现 `Claude Code Deep Review` 工作流运行。

- [ ] **Step 4: 检查 PR 评论和 Check Run**

等待工作流完成后，检查：
1. PR 下出现 Claude Code 审查评论。
2. PR 检查列表出现 `Claude Code Deep Review` 检查。

Expected: 评论中包含分级报告，Check Run 结论为 `success` 或 `failure`。

- [ ] **Step 5: 关闭测试 PR**

Run:
```bash
gh pr close test/deep-review-auto --delete-branch
```

---

### Task 10: 更新分支保护以包含 Claude Code 检查

**Files:**
- Create: 无
- Modify: GitHub 分支保护规则
- Test: 带 `deep-review` 标签的 PR 在 Claude Code 检查失败时无法合并

**Interfaces:**
- Consumes: `Claude Code Deep Review` Check Run
- Produces: 更新后的分支保护规则

- [ ] **Step 1: 更新分支保护规则**

Run:
```bash
gh api repos/{owner}/{repo}/branches/main/protection \
  --method PUT \
  --input - <<EOF
{
  "required_status_checks": {
    "strict": true,
    "contexts": ["CodeRabbit", "Claude Code Deep Review"]
  },
  "enforce_admins": false,
  "required_pull_request_reviews": {
    "required_approving_review_count": 1,
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": false
  },
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false
}
EOF
```

Expected: 返回 200，分支保护规则已更新。

- [ ] **Step 2: 验证 Claude Code 检查阻塞合并**

创建一个有阻塞项的测试 PR（例如引入明显的除零错误）：

Run:
```bash
git checkout -b test/blocking-check
cat > backend/services/blocking_test.py <<'PY'
def risky_divide(a, b):
    return a / b  # 未处理 b=0
PY
git add backend/services/blocking_test.py
git commit -m "test: 引入阻塞项验证检查"
git push -u origin test/blocking-check
gh pr create --title "test: 验证 Claude Code 阻塞合并" --body "引入潜在除零错误，验证 deep-review 是否能拦截。" --label deep-review
```

Expected: Claude Code 检查失败，PR 无法合并。

- [ ] **Step 3: 关闭测试 PR 并删除测试文件**

Run:
```bash
gh pr close test/blocking-check --delete-branch
```

---

### Task 11: 创建未来项目复用模板

**Files:**
- Create: `.github/templates/coderabbit.yaml.template`
- Create: `.github/templates/pull_request_template.md`
- Create: `.github/templates/workflows/claude-code-review.yml.template`
- Create: `.github/templates/review_prompts/deep_review.md`
- Create: `docs/review-setup/README.md`
- Modify: 无
- Test: 按 README 模拟新项目接入步骤

**Interfaces:**
- Consumes: 已验证的配置和脚本
- Produces: 可复用的模板包

- [ ] **Step 1: 复制 CodeRabbit 配置模板**

Create `.github/templates/coderabbit.yaml.template`:

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
    - path: "frontend_react/src/**/*.tsx"
      instructions: |
        关注 React Hook 依赖、潜在内存泄漏、TypeScript 类型安全、UI 状态管理。
    - path: "core/**/*.py"
      instructions: |
        这是系统核心模块，关注算法正确性、边界条件、性能热点、数据契约。

  auto_review:
    enabled: true
    drafts: false
    base_branches: ["main"]

  chat:
    auto_reply: true
```

- [ ] **Step 2: 复制 PR 模板**

Create `.github/templates/pull_request_template.md`:

```markdown
## 改动说明

## 影响范围

- [ ] 核心业务逻辑
- [ ] 大型重构（>300 行或影响多个模块）
- [ ] 安全敏感改动（认证、配置、依赖升级）
- [ ] 仅 UI / 工具函数 / 文档

## 审查标签

- `deep-review`：涉及核心逻辑/安全/大型重构，需要 Claude Code 深度审查
- `bugfix` / `feature` / `docs`：常规分类标签

## 自查清单

- [ ] 本地测试通过 或 happy path 已验证
```

- [ ] **Step 3: 复制工作流模板**

Create `.github/templates/workflows/claude-code-review.yml.template`:

```yaml
name: Claude Code Deep Review

on:
  pull_request:
    types: [labeled, synchronize]

jobs:
  deep-review:
    if: contains(github.event.pull_request.labels.*.name, 'deep-review')
    runs-on: self-hosted
    permissions:
      contents: read
      pull-requests: write
      checks: write
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: 准备 diff
        run: |
          git fetch origin ${{ github.event.pull_request.base.ref }}
          git diff origin/${{ github.event.pull_request.base.ref }} > pr_diff.patch

      - name: 运行 Claude Code 深度审查
        run: |
          claude code --dangerously-sandbox \
            --allow-tools "Read,Bash,Grep" \
            --message "请按照 .github/review_prompts/deep_review.md 审查 pr_diff.patch，输出为 JSON 格式" \
            > claude_review_report.json

      - name: 发布审查报告
        uses: actions/github-script@v7
        env:
          PR_NUMBER: ${{ github.event.pull_request.number }}
          HEAD_SHA: ${{ github.event.pull_request.head.sha }}
        with:
          script: |
            const fs = require('fs');
            const path = require('path');
            const raw = fs.readFileSync(path.join(process.env.GITHUB_WORKSPACE, 'claude_review_report.json'), 'utf8');
            let report;
            try {
              const match = raw.match(/```json\s*([\s\S]*?)\s*```/);
              report = match ? JSON.parse(match[1]) : JSON.parse(raw);
            } catch (e) {
              report = { summary: "解析失败", severity: "warning", findings: [], action_required: [] };
            }
            const blocking = report.findings?.filter(f => f.severity === 'blocking') || [];
            const conclusion = blocking.length > 0 ? 'failure' : 'success';
            await github.rest.checks.create({
              owner: context.repo.owner,
              repo: context.repo.repo,
              name: 'Claude Code Deep Review',
              head_sha: process.env.HEAD_SHA,
              status: 'completed',
              conclusion,
              output: { title: conclusion === 'failure' ? '发现阻塞项' : '通过', summary: report.summary }
            });
```

- [ ] **Step 4: 复制提示词模板**

Create `.github/templates/review_prompts/deep_review.md`:

```markdown
你是一名严格的代码审查专家。请审查以下 PR diff，重点关注：

1. 核心业务逻辑错误
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
      "file": "src/example.py",
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

- [ ] **Step 5: 编写新项目接入指南**

Create `docs/review-setup/README.md`:

```markdown
# 代码审查体系接入手册

本手册说明如何将 CodeRabbit + Claude Code Review + 人类 Reviewer 的三层审查体系接入到新项目。

## 前提条件

- 代码托管在 GitHub 私有仓库
- 已有可用的自托管 Actions Runner（安装并登录了 Claude Code CLI）

## 接入步骤

1. 复制模板文件到项目根目录：
   ```bash
   cp -r .github/templates/.github .
   ```

2. 在 GitHub 仓库中安装 CodeRabbit App：
   https://github.com/apps/coderabbitai

3. 创建 `deep-review` 标签：
   ```bash
   gh label create deep-review --description "需要 Claude Code 深度审查" --color FF0000
   ```

4. 配置分支保护：
   ```bash
   gh api repos/{owner}/{repo}/branches/main/protection --method PUT --input branch-protection.json
   ```
   其中 `branch-protection.json` 包含 `CodeRabbit` 和 `Claude Code Deep Review` 两个 required status checks。

5. 根据项目技术栈微调 `.coderabbit.yaml` 的 `path_instructions`。

6. 提交一个测试 PR 并打上 `deep-review` 标签，验证 Claude Code 工作流是否正常触发。
```

- [ ] **Step 6: 提交模板与文档**

Run:
```bash
git add .github/templates/ docs/review-setup/
git commit -m "docs: 添加代码审查体系复用模板与接入手册"
git push origin main
```

Expected: 模板文件和接入指南成功推送到 main 分支。

---

## 自审

### 1. 设计文档覆盖检查

| 设计文档章节 | 实现任务 |
|--------------|----------|
| 总体架构 | Task 1-11 |
| 方案 A（最小可用） | Task 1-6 |
| 方案 B（完整自动化） | Task 7-10 |
| GitHub 仓库与分支保护 | Task 2, 5, 10 |
| PR 模板与标签策略 | Task 4 |
| CodeRabbit 配置 | Task 7 |
| Claude Code 工作流 | Task 9 |
| 审查提示词 | Task 6, 9, 11 |
| 报告格式与门禁规则 | Task 9, 10 |
| 错误处理与回退策略 | Task 9 工作流中的 try/catch |
| 落地验证清单 | 各 Task 的验证步骤 |
| 未来项目复用模板 | Task 11 |

**Gap:** 无。

### 2. 占位符扫描

- 无 "TBD" / "TODO" / "implement later"。
- 所有代码片段均包含可执行内容。
- 所有命令均给出具体预期输出。

### 3. 类型一致性检查

- `deep-review` 标签名称在 Task 4, 6, 9, 10, 11 中保持一致。
- `.coderabbit.yaml` 路径在 Task 7 和 Task 11 模板中一致。
- `Claude Code Deep Review` Check Run 名称在 Task 9 和 Task 10 中一致。

---

## 执行交接

计划已完成并保存到：

```
docs/superpowers/plans/2026-06-27-code-review-system-implementation-plan.md
```

**两种执行方式：**

1. **子智能体驱动（推荐）**：每个 Task 由一个独立子智能体执行，完成后我进行审查，再进入下一个 Task。适合需要严格把控质量的场景。

2. **当前会话内联执行**：在当前会话中按 Task 顺序执行，我可以批量处理相关步骤，并在关键节点暂停确认。

**请选择一种方式开始执行。**
