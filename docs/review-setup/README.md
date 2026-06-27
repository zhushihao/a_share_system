# 代码审查体系接入手册

本手册说明如何将 CodeRabbit + Claude Code Review + 人类 Reviewer 的三层审查体系接入到新项目。

## 前提条件

- 代码托管在 GitHub 仓库
- 已有可用的自托管 Actions Runner（安装并登录了 Claude Code CLI）
- Runner 已设置 `ANTHROPIC_API_KEY` 和 `ANTHROPIC_BASE_URL` 环境变量，或仓库已配置同名 secrets

## 接入步骤

1. 复制模板文件到项目根目录：
   ```bash
   cp .github/templates/coderabbit.yaml.template .coderabbit.yaml
   cp .github/templates/pull_request_template.md .github/pull_request_template.md
   cp .github/templates/workflows/claude-code-review.yml.template .github/workflows/claude-code-review.yml
   cp .github/templates/review_prompts/deep_review.md .github/review_prompts/deep_review.md
   ```

2. 在 GitHub 仓库中安装 CodeRabbit App：
   https://github.com/apps/coderabbitai

3. 创建 `deep-review` 标签：
   ```bash
   gh label create deep-review --description "需要 Claude Code 深度审查" --color FF0000
   ```

4. 配置分支保护：
   ```bash
   gh api repos/{owner}/{repo}/branches/main/protection --method PUT --input - <<EOF
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

5. 根据项目技术栈微调 `.coderabbit.yaml` 的 `path_instructions`。

6. 提交一个测试 PR 并打上 `deep-review` 标签，验证 Claude Code 工作流是否正常触发。

## 日常用法

- 常规 PR：无需特殊标签，CodeRabbit 会自动审查。
- 涉及核心逻辑/安全/大型重构的 PR：在 PR 描述中勾选对应项，维护者添加 `deep-review` 标签，Claude Code 会自动进行深度审查。
- 人类 reviewer 保留最终合并决策权。
