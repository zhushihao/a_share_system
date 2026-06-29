#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Quant Workbench 报告问题自动修复器

每小时检查 reports/selfcheck/ 和 reports/ux/ 中的最新报告，
读取【发现的问题】，按 P0→P1→P2 优先级调用 LLM 修复，
修复完成后在原报告末尾追加【修复记录】。

环境变量（任选其一）：
  ANTHROPIC_API_KEY  -> Claude API（优先）
  KIMI_API_KEY       -> Moonshot Kimi API
  OPENAI_API_KEY     -> OpenAI 兼容 API

支持配置（可选）：
  LLM_MODEL          -> 模型名称，默认 claude-sonnet-4-6
  LLM_BASE_URL       -> 自定义 base URL
  LLM_MAX_TOKENS     -> 最大 token 数，默认 4096
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

REPORT_DIRS = {
    "selfcheck": PROJECT_ROOT / "reports" / "selfcheck",
    "ux": PROJECT_ROOT / "reports" / "ux",
}

# 报告文件名匹配模式
REPORT_PATTERNS = {
    "selfcheck": re.compile(r"SYSTEM_LOOP_CHECK_REPORT_(\d{4}-\d{2}-\d{2}_\d{4})\.md"),
    "ux": re.compile(r"UX_CHECK_REPORT_(\d{4}-\d{2}-\d{2}_\d{4})\.md"),
}

# 允许 LLM 修改的文件扩展名
EDITABLE_EXTENSIONS = {".py", ".tsx", ".ts", ".jsx", ".js", ".css", ".html", ".md"}


def _log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")


def find_latest_report(report_dir: Path, pattern: re.Pattern) -> Optional[Path]:
    """按文件名中的时间戳找出最新报告"""
    if not report_dir.exists():
        return None

    candidates: List[Tuple[Path, datetime]] = []
    for fpath in report_dir.glob("*.md"):
        m = pattern.search(fpath.name)
        if not m:
            continue
        try:
            dt = datetime.strptime(m.group(1), "%Y-%m-%d_%H%M")
            candidates.append((fpath, dt))
        except Exception:
            pass

    if not candidates:
        return None
    return max(candidates, key=lambda x: x[1])[0]


def _find_section(text: str, header: str) -> str:
    """提取 Markdown 中某个章节的内容，允许标题前有编号、后有括号注释"""
    # 支持：## 一、发现的问题（按优先级排序） 或 ### 问题汇总 或 【发现的问题】
    # 终止于下一个 ## 标题、水平分隔线 --- 或文档末尾；注意不把 ### 问题标题误当章节
    pattern = re.compile(
        rf"(?:^|\n)(?:【{re.escape(header)}】|##\s.*?{re.escape(header)}(?:\s*[（(].*?[）)])?|###\s.*?{re.escape(header)}(?:\s*[（(].*?[）)])?)\s*\n"
        rf"(.*?)"
        rf"(?=(?:\n(?:【|##\s))|(?:\n---\s*\n)|$)",
        re.S,
    )
    m = pattern.search(text)
    return m.group(1).strip() if m else ""


def parse_issues(report_path: Path) -> List[Dict]:
    """
    解析报告中的问题列表，返回按 P0→P1→P2 排序的字典列表。
    每个问题包含：priority, title, description, files, fix_suggestion, verification
    """
    text = report_path.read_text(encoding="utf-8")

    # 不同报告可能使用不同的章节标题
    for header in ("发现的问题", "问题汇总"):
        section = _find_section(text, header)
        if section:
            break
    else:
        return []

    # 问题通常以以下格式开头：
    # ### 🔴 P0 - 标题
    # ### 1. 🔴 P0 - 标题
    # ### P2 - 1: 标题
    # ### P0 - 标题
    issue_blocks = re.split(r"\n(?=###\s*(?:\d+\.\s*)?(?:[🔴🟠🟡🟢]\s*)?P\d+(?:\s*[-–:]\s*\d+)?)", section)

    priority_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    issues: List[Dict] = []

    for block in issue_blocks:
        block = block.strip()
        if not block:
            continue

        # 提取优先级和标题
        header_match = re.match(
            r"###\s*(?:\d+\.\s*)?(?:[🔴🟠🟡🟢]\s*)?(P\d+)(?:\s*[-–:]\s*\d+)?\s*[-–:]\s*(.+)",
            block,
        )
        if not header_match:
            continue

        priority = header_match.group(1).upper()
        title = header_match.group(2).strip()

        # 提取涉及文件（支持 **涉及文件**： 或 涉及文件： 格式）
        files = []
        file_section_match = re.search(r"[-*]\s*[*_]*涉及文件[*_]*[：:]\s*(.+?)(?=\n\s*[-*]|\n\s*###|\Z)", block, re.S)
        if file_section_match:
            file_text = file_section_match.group(1)
            # 支持多行文件列表
            for line in file_text.splitlines():
                line = line.strip().strip(",;，")
                if not line:
                    continue
                # 取路径部分
                path_match = re.search(r"([a-zA-Z0-9_\-./]+(?:\.[a-zA-Z0-9]+)?)", line)
                if path_match:
                    candidate = path_match.group(1)
                    if "/" in candidate or "\\" in candidate or "." in candidate:
                        files.append(candidate)

        # 提取建议修复
        fix_match = re.search(r"[-*]\s*[*_]*建议修复[*_]*[：:]\s*(.+?)(?=\n\s*[-*]|\n\s*###|\Z)", block, re.S)
        fix_suggestion = fix_match.group(1).strip() if fix_match else ""

        # 提取验证步骤
        verify_match = re.search(r"[-*]\s*[*_]*验证步骤[*_]*[：:]\s*(.+?)(?=\n\s*[-*]|\n\s*###|\Z)", block, re.S)
        verification = verify_match.group(1).strip() if verify_match else ""

        # 去重并规范化文件路径
        normalized_files = []
        for f in files:
            f = f.replace("\\", "/").strip()
            if f and f not in normalized_files:
                normalized_files.append(f)

        issues.append({
            "priority": priority,
            "title": title,
            "description": block,
            "files": normalized_files,
            "fix_suggestion": fix_suggestion,
            "verification": verification,
        })

    issues.sort(key=lambda x: priority_order.get(x["priority"], 99))
    return issues


def _resolve_file_path(file_str: str) -> Optional[Path]:
    """把相对路径解析为项目根目录下的绝对路径"""
    if os.path.isabs(file_str):
        p = Path(file_str)
    else:
        p = PROJECT_ROOT / file_str
    return p if p.exists() else None


def _is_editable_file(p: Path) -> bool:
    """检查文件类型是否允许自动修改"""
    return p.suffix.lower() in EDITABLE_EXTENSIONS


def _read_file(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _backup_file(p: Path) -> Path:
    """创建 .bak 备份，若已存在则复用"""
    bak = p.with_suffix(p.suffix + ".bak")
    if not bak.exists():
        shutil.copy2(p, bak)
    return bak


def _restore_backup(p: Path) -> None:
    bak = p.with_suffix(p.suffix + ".bak")
    if bak.exists():
        shutil.copy2(bak, p)


def _clean_backup(p: Path) -> None:
    bak = p.with_suffix(p.suffix + ".bak")
    if bak.exists():
        bak.unlink()


def _build_llm_prompt(issue: Dict, files_content: Dict[str, str]) -> str:
    """构造给 LLM 的修复 prompt"""
    files_block = ""
    for rel_path, content in files_content.items():
        files_block += f"\n--- 文件: {rel_path} ---\n```\n{content}\n```\n"

    prompt = f"""你是 Quant Workbench 的代码修复助手。请根据以下问题描述修复代码。

【问题】
优先级：{issue['priority']}
标题：{issue['title']}
建议修复：
{issue['fix_suggestion'] or '请根据问题描述给出最小修复'}
验证步骤：
{issue['verification'] or '确保代码可运行且问题已解决'}

【涉及文件及当前内容】{files_block}

【要求】
1. 只修改上述涉及文件，严禁创建或修改其他文件。
2. 应用最小化修复，不要重构无关代码。
3. 保持原有代码风格、缩进和命名习惯。
4. 返回 JSON 数组格式，每个元素包含 file（相对项目根目录的路径）和 content（完整新内容）：
   [{{"file": "frontend_react/src/App.tsx", "content": "..."}}]
5. 不要返回任何解释文字，只返回 JSON。
"""
    return prompt


def _detect_provider() -> Tuple[str, str, str]:
    """根据环境变量检测可用的 LLM provider，返回 (provider, api_key, base_url, model)"""
    model = os.environ.get("LLM_MODEL")
    base_url = os.environ.get("LLM_BASE_URL", "")

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    kimi_key = os.environ.get("KIMI_API_KEY", "")
    openai_key = os.environ.get("OPENAI_API_KEY", "")

    # 如果 ANTHROPIC_API_KEY 的值明显是 Kimi key，则交给 Kimi 处理
    if anthropic_key.strip().startswith("sk-kimi"):
        kimi_key = anthropic_key
        anthropic_key = ""

    if anthropic_key:
        return (
            "anthropic",
            anthropic_key,
            base_url or "https://api.anthropic.com/v1",
            model or "claude-sonnet-4-6",
        )
    if kimi_key:
        return (
            "kimi",
            kimi_key,
            base_url or "https://api.moonshot.cn/v1",
            model or "moonshot-v1-8k",
        )
    if openai_key:
        return (
            "openai",
            openai_key,
            base_url or "https://api.openai.com/v1",
            model or "gpt-4o-mini",
        )
    raise RuntimeError("未配置任何 LLM API Key（ANTHROPIC_API_KEY / KIMI_API_KEY / OPENAI_API_KEY）")


def _call_llm(prompt: str) -> str:
    """调用 LLM API 返回原始文本"""
    provider, api_key, base_url, model = _detect_provider()
    _log(f"使用 LLM provider: {provider}, model: {model}")

    if provider == "anthropic":
        return _call_anthropic(api_key, base_url, model, prompt)
    elif provider == "kimi":
        return _call_openai_compatible(api_key, base_url, model, prompt, "Kimi")
    else:
        return _call_openai_compatible(api_key, base_url, model, prompt, "OpenAI")


def _call_anthropic(api_key: str, base_url: str, model: str, prompt: str) -> str:
    url = f"{base_url.rstrip('/')}/messages"
    body = {
        "model": model,
        "max_tokens": int(os.environ.get("LLM_MAX_TOKENS", "4096")),
        "messages": [{"role": "user", "content": prompt}],
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        return data["content"][0]["text"]


def _call_openai_compatible(api_key: str, base_url: str, model: str, prompt: str, label: str) -> str:
    url = f"{base_url.rstrip('/')}/chat/completions"
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是一个资深的 Python/TypeScript 量化系统工程师，擅长最小化修复代码问题。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": int(os.environ.get("LLM_MAX_TOKENS", "4096")),
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "content-type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]


def _extract_json_array(text: str) -> List[Dict]:
    """从 LLM 返回文本中提取 JSON 数组"""
    text = text.strip()
    # 尝试直接解析
    try:
        return json.loads(text)
    except Exception:
        pass

    # 尝试去掉 markdown 代码块
    code_block = re.search(r"```(?:json)?\s*(\[.*?)```", text, re.S)
    if code_block:
        try:
            return json.loads(code_block.group(1).strip())
        except Exception:
            pass

    # 尝试找第一个 [ ... ] 数组
    array_match = re.search(r"(\[.*\])", text, re.S)
    if array_match:
        try:
            return json.loads(array_match.group(1).strip())
        except Exception:
            pass

    raise ValueError(f"无法从 LLM 响应中解析 JSON 数组: {text[:200]}")


def _verify_file(p: Path) -> Tuple[bool, str]:
    """对修改后的文件做基础验证"""
    suffix = p.suffix.lower()
    if suffix == ".py":
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(p)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            return False, f"Python 语法检查失败: {result.stderr.strip()[:200]}"
        return True, "Python 语法检查通过"
    elif suffix in {".tsx", ".ts", ".jsx", ".js"}:
        # 如果项目里有 TypeScript，尝试运行 tsc --noEmit（不强制）
        tsc = PROJECT_ROOT / "frontend_react" / "node_modules" / ".bin" / "tsc"
        if tsc.exists():
            result = subprocess.run(
                [str(tsc), "--noEmit", "--project", str(PROJECT_ROOT / "frontend_react" / "tsconfig.json")],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                return False, f"TypeScript 检查失败: {result.stderr.strip()[:300]}"
            return True, "TypeScript 检查通过"
        return True, "未配置 TypeScript 检查，跳过"
    return True, "无需验证"


def _apply_issue_fix(issue: Dict) -> Dict:
    """对单个问题调用 LLM 并应用修复，返回修复记录"""
    record = {
        "priority": issue["priority"],
        "title": issue["title"],
        "files": issue["files"],
        "status": "skipped",
        "message": "",
        "modified_files": [],
    }

    if not issue["files"]:
        record["status"] = "skipped"
        record["message"] = "问题未指明涉及文件，无法自动修复"
        return record

    # 收集涉及文件内容
    files_content: Dict[str, str] = {}
    file_paths: Dict[str, Path] = {}
    for f in issue["files"]:
        p = _resolve_file_path(f)
        if p is None:
            record["status"] = "skipped"
            record["message"] = f"涉及文件不存在: {f}"
            return record
        if not _is_editable_file(p):
            record["status"] = "skipped"
            record["message"] = f"文件类型不允许自动修改: {f}"
            return record
        rel = str(p.relative_to(PROJECT_ROOT)).replace("\\", "/")
        files_content[rel] = _read_file(p)
        file_paths[rel] = p

    prompt = _build_llm_prompt(issue, files_content)

    try:
        raw_response = _call_llm(prompt)
        changes = _extract_json_array(raw_response)
    except Exception as e:
        record["status"] = "failed"
        record["message"] = f"LLM 调用或解析失败: {e}"
        return record

    if not isinstance(changes, list):
        record["status"] = "failed"
        record["message"] = f"LLM 返回格式错误，期望数组，得到 {type(changes).__name__}"
        return record

    # 备份所有待修改文件
    for rel_path in [c.get("file") for c in changes if c.get("file")]:
        if rel_path in file_paths:
            _backup_file(file_paths[rel_path])

    applied_files = []
    try:
        for change in changes:
            rel_path = change.get("file", "").replace("\\", "/")
            new_content = change.get("content", "")
            if not rel_path or new_content is None:
                continue

            if rel_path not in file_paths:
                record["status"] = "failed"
                record["message"] = f"LLM 返回了未授权的文件: {rel_path}"
                raise RuntimeError("unauthorized file")

            p = file_paths[rel_path]
            p.write_text(new_content, encoding="utf-8")
            applied_files.append(rel_path)

        # 验证
        verify_messages = []
        all_ok = True
        for rel_path in applied_files:
            ok, msg = _verify_file(file_paths[rel_path])
            verify_messages.append(f"{rel_path}: {msg}")
            if not ok:
                all_ok = False

        if not all_ok:
            raise RuntimeError("verification failed: " + "; ".join(verify_messages))

        # 验证通过，清理备份
        for rel_path in applied_files:
            _clean_backup(file_paths[rel_path])

        record["status"] = "fixed"
        record["message"] = "; ".join(verify_messages)
        record["modified_files"] = applied_files

    except Exception as e:
        # 回滚所有修改
        for rel_path in applied_files:
            if rel_path in file_paths:
                _restore_backup(file_paths[rel_path])
        for rel_path in [c.get("file") for c in changes if c.get("file")]:
            if rel_path in file_paths:
                _clean_backup(file_paths[rel_path])

        if record["status"] != "failed":
            record["status"] = "failed"
            record["message"] = f"应用或验证失败并已回滚: {e}"

    return record


def _append_fix_record(report_path: Path, records: List[Dict]) -> None:
    """在原报告末尾追加【修复记录】"""
    if not records:
        return

    text = report_path.read_text(encoding="utf-8")
    marker = "【修复记录】"
    if marker in text:
        # 已有修复记录，追加到末尾
        text = text.rstrip() + "\n\n"
    else:
        text = text.rstrip() + "\n\n---\n\n" + marker + "\n"

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [f"\n### 修复批次 - {now}\n"]
    for r in records:
        lines.append(f"- **{r['priority']}** {r['title']}")
        lines.append(f"  - 状态：{r['status']}")
        lines.append(f"  - 涉及文件：{', '.join(r['files']) if r['files'] else '无'}")
        if r.get("modified_files"):
            lines.append(f"  - 已修改：{', '.join(r['modified_files'])}")
        lines.append(f"  - 结果：{r['message']}")
        lines.append("")

    report_path.write_text(text + "\n".join(lines), encoding="utf-8")


def _acquire_lock() -> bool:
    """单例锁，防止上一轮还没跑完就启动新一轮"""
    lock_dir = PROJECT_ROOT / "data" / "backend"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_file = lock_dir / "report_fixer.lock"
    try:
        if lock_file.exists():
            try:
                old_pid = int(lock_file.read_text(encoding="utf-8").strip())
                if old_pid != os.getpid():
                    result = subprocess.run(
                        ["tasklist", "/FI", f"PID eq {old_pid}", "/NH"],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    if str(old_pid) in result.stdout:
                        return False
            except Exception:
                pass
        lock_file.write_text(str(os.getpid()), encoding="utf-8")
        return True
    except Exception as e:
        _log(f"无法获取锁: {e}")
        return False


def _release_lock() -> None:
    lock_file = PROJECT_ROOT / "data" / "backend" / "report_fixer.lock"
    try:
        if lock_file.exists() and lock_file.read_text(encoding="utf-8").strip() == str(os.getpid()):
            lock_file.unlink()
    except Exception:
        pass


def process_report(report_path: Path) -> List[Dict]:
    """处理单份报告，返回修复记录列表"""
    _log(f"处理报告: {report_path.name}")
    issues = parse_issues(report_path)
    if not issues:
        _log("报告中没有问题，跳过")
        return []

    _log(f"发现 {len(issues)} 个问题，按 P0→P1→P2 排序处理")

    # 检查是否已有修复记录且全部完成
    text = report_path.read_text(encoding="utf-8")
    if "【修复记录】" in text and "状态：failed" not in text and "状态：skipped" not in text:
        _log("报告已有修复记录且无失败项，跳过")
        return []

    records: List[Dict] = []
    for issue in issues:
        _log(f"处理 {issue['priority']} 问题: {issue['title']}")
        record = _apply_issue_fix(issue)
        records.append(record)
        _log(f"结果: {record['status']} - {record['message'][:120]}")

    if records:
        _append_fix_record(report_path, records)
        _log(f"已追加修复记录到: {report_path.name}")

    return records


def _dry_run() -> None:
    """只解析最新报告并打印将要处理的问题，不调用 LLM"""
    _log("=== DRY RUN 模式：只解析问题，不执行修复 ===")
    for report_type, report_dir in REPORT_DIRS.items():
        pattern = REPORT_PATTERNS[report_type]
        latest = find_latest_report(report_dir, pattern)
        if latest is None:
            _log(f"未找到 {report_type} 最新报告")
            continue
        _log(f"\n[{report_type}] 最新报告: {latest.name}")
        issues = parse_issues(latest)
        if not issues:
            _log("  没有问题")
            continue
        for issue in issues:
            _log(f"  {issue['priority']} - {issue['title']}")
            _log(f"    涉及文件: {', '.join(issue['files']) if issue['files'] else '无'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Quant Workbench 报告问题自动修复器")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只解析报告并打印问题，不调用 LLM 或修改文件",
    )
    args = parser.parse_args()

    if args.dry_run:
        _dry_run()
        return

    if not _acquire_lock():
        _log("上一轮修复尚未结束，本次跳过")
        return

    try:
        _log("=== 报告问题自动修复开始 ===")

        all_records: Dict[str, List[Dict]] = {}
        for report_type, report_dir in REPORT_DIRS.items():
            pattern = REPORT_PATTERNS[report_type]
            latest = find_latest_report(report_dir, pattern)
            if latest is None:
                _log(f"未找到 {report_type} 最新报告")
                continue
            all_records[report_type] = process_report(latest)

        total_fixed = sum(1 for recs in all_records.values() for r in recs if r["status"] == "fixed")
        total_failed = sum(1 for recs in all_records.values() for r in recs if r["status"] == "failed")
        total_skipped = sum(1 for recs in all_records.values() for r in recs if r["status"] == "skipped")

        _log(
            f"=== 报告问题自动修复结束 === "
            f"fixed={total_fixed}, failed={total_failed}, skipped={total_skipped}"
        )
    finally:
        _release_lock()


if __name__ == "__main__":
    main()
