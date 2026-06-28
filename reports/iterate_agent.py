# -*- coding: utf-8 -*-
"""
自主迭代代理

读取最新的自检报告，匹配规则库，自动修复低风险问题，
对未覆盖问题生成 LLM 修复草案或人工待办。
"""

import importlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

# 确保项目根目录在 sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from reports.rules import Rule, api_health, api_smoke_tests, run_pytest


def _discover_rules() -> List[Rule]:
    """自动发现 reports/rules/ 下的所有规则"""
    rules_dir = PROJECT_ROOT / "reports" / "rules"
    rules: List[Rule] = []
    for fname in sorted(rules_dir.glob("*.py")):
        if fname.name.startswith("_"):
            continue
        module_name = f"reports.rules.{fname.stem}"
        try:
            mod = importlib.import_module(module_name)
            for attr in dir(mod):
                obj = getattr(mod, attr)
                if (
                    isinstance(obj, type)
                    and issubclass(obj, Rule)
                    and obj is not Rule
                    and obj.name
                ):
                    rules.append(obj())
        except Exception as e:
            print(f"[WARN] 加载规则 {module_name} 失败: {e}")
    return rules


def _sort_rules(rules: List[Rule]) -> List[Rule]:
    """backend_restart 优先；其余按 priority 升序，再按风险等级 low -> medium -> high"""
    order = {"low": 0, "medium": 1, "high": 2}
    return sorted(
        rules,
        key=lambda r: (
            0 if r.name == "backend_restart" else 1,
            r.priority,
            order.get(r.risk, 99),
        ),
    )


def parse_report(report_path: Path) -> Dict[str, List[str]]:
    """简单解析 Markdown 自检报告，提取问题与建议"""
    text = report_path.read_text(encoding="utf-8")

    def extract_section(header_pattern: str) -> List[str]:
        items = []
        # 匹配 "【XXX】" 或 "## XXX" 开头到下一个同等级标题之间的行
        pattern = re.compile(rf"({re.escape(header_pattern)}).*?\n(.*?)(?=\n【|\n## |\n===|$)", re.S)
        for m in pattern.finditer(text):
            section = m.group(2)
            for line in section.splitlines():
                line = line.strip()
                if not line:
                    continue
                # 收集列表项、编号项或独立短句
                if line.startswith(("- ", "* ", "1. ", "2. ", "3. ", "4. ", "5. ", "6. ", "7. ", "8. ", "9. ")):
                    items.append(re.sub(r"^[-*\d.\s]+", "", line).strip())
                elif line.startswith("⚠️") or line.startswith("❌"):
                    items.append(line)
        return items

    issues = extract_section("【发现的问题】")
    suggestions = extract_section("【优化建议】")
    critical = extract_section("Critical")
    important = extract_section("Important")

    return {
        "issues": issues,
        "suggestions": suggestions,
        "critical": critical,
        "important": important,
        "all": issues + suggestions + critical + important,
    }


def _match_rules(rules: List[Rule], issue_texts: List[str]) -> set:
    """根据问题文本匹配规则"""
    matched = set()
    for rule in rules:
        for text in issue_texts:
            if rule.matches(text):
                matched.add(rule.name)
                break
    return matched


def _get_backend_pid() -> int:
    """通过 netstat 查找监听 5889 的进程 PID"""
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        for line in result.stdout.splitlines():
            if ":5889" in line and "LISTENING" in line:
                m = re.search(r"LISTENING\s+(\d+)", line)
                if m:
                    return int(m.group(1))
    except Exception:
        pass
    return 0


def _restart_backend() -> Tuple[bool, str]:
    """结束监听 5889 的后端进程并重新启动"""
    pid = _get_backend_pid()
    if pid:
        try:
            subprocess.run(
                ["taskkill", "//PID", str(pid), "//F"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except Exception as e:
            return False, f"结束旧后端 PID {pid} 失败: {e}"

    # 等待端口释放
    for _ in range(10):
        if _get_backend_pid() == 0:
            break
        time.sleep(0.5)

    log_path = PROJECT_ROOT / "backend.log"
    try:
        proc = subprocess.Popen(
            ["pythonw", "-m", "backend.main"],
            cwd=PROJECT_ROOT,
            stdout=open(log_path, "a", encoding="utf-8"),
            stderr=subprocess.STDOUT,
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        )
    except Exception as e:
        return False, f"启动后端失败: {e}"

    for i in range(20):
        ok, _ = api_health(timeout=5)
        if ok:
            return True, f"后端已重启 (pid={proc.pid})"
        time.sleep(2)
    return False, "后端重启后健康检查未通过"


def _generate_llm_draft(unmatched_issues: List[str]) -> Optional[str]:
    """若配置了 AI API Key，则生成修复草案；否则返回 None"""
    api_key = os.environ.get("KIMI_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        try:
            from backend.config import settings
            api_key = getattr(settings, "AI_API_KEY", "")
        except Exception:
            pass
    if not api_key:
        return None

    prompt = (
        "你是 Quant Workbench 的代码审查助手。以下是从系统自检报告中发现的问题，"
        "请为每个问题给出：1) 根因分析；2) 建议修改的文件和代码片段（仅描述，不直接执行）；"
        "3) 验证方法。注意：这些草案需要人工审批后才能执行。\n\n"
        + "\n".join(f"- {issue}" for issue in unmatched_issues)
    )

    # 尝试调用 Moonshot / OpenAI 兼容接口
    base_url = os.environ.get("KIMI_BASE_URL", "https://api.moonshot.cn/v1")
    try:
        from backend.config import settings
        base_url = getattr(settings, "AI_BASE_URL", base_url)
    except Exception:
        pass

    try:
        req = urllib.request.Request(
            f"{base_url.rstrip('/')}/chat/completions",
            data=json.dumps(
                {
                    "model": os.environ.get("KIMI_MODEL", "moonshot-v1-8k"),
                    "messages": [
                        {"role": "system", "content": "你是一个资深的 Python/金融量化系统工程师。"},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 2000,
                }
            ).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
            return content
    except Exception as e:
        return f"LLM 草案生成失败: {e}"


def _find_latest_report(report_dirs: List[Path]) -> Optional[Tuple[Path, datetime]]:
    """从 reports/ 及其子目录中按文件名解析出最新的检查报告"""
    patterns = [
        (r"SYSTEM_LOOP_CHECK_REPORT_(\d{4}-\d{2}-\d{2}_\d{4})\.md", "%Y-%m-%d_%H%M"),
        (r"TDX_ALIGNMENT_SELF_CHECK_(\d{8}_\d{4})\.md", "%Y%m%d_%H%M"),
        (r"SELF_CHECK_REPORT_(\d{8})_EXECUTED\.md", "%Y%m%d"),
        (r"REVIEW_COMPREHENSIVE_(\d{4}-\d{2}-\d{2})\.md", "%Y-%m-%d"),
        (r"TDX_GAP_REPORT_(\d{8})\.md", "%Y%m%d"),
        (r"UX_CHECK_REPORT_(\d{4}-\d{2}-\d{2}_\d{4})\.md", "%Y-%m-%d_%H%M"),
    ]

    candidates: List[Tuple[Path, datetime]] = []
    for report_dir in report_dirs:
        if not report_dir.exists():
            continue
        for fpath in report_dir.glob("*.md"):
            for regex, fmt in patterns:
                m = re.search(regex, fpath.name)
                if m:
                    try:
                        dt = datetime.strptime(m.group(1), fmt)
                        candidates.append((fpath, dt))
                    except Exception:
                        pass
                    break

    if not candidates:
        return None
    return max(candidates, key=lambda x: x[1])


def run_iteration(report_path: Optional[Path | Sequence[Path]] = None) -> Path:
    """执行一次自主迭代；可接收单个报告或多份报告，并自动补充最新检查报告"""
    now = datetime.now()
    ts = now.strftime("%Y%m%d_%H%M")
    iteration_report_path = PROJECT_ROOT / "reports" / "selfcheck" / f"ITERATION_REPORT_v2.0_EXECUTED_{ts}.md"

    rules = _sort_rules(_discover_rules())

    # 支持传入单个报告或报告列表
    report_paths: List[Path] = []
    if isinstance(report_path, list):
        report_paths = [p for p in report_path if isinstance(p, Path)]
    elif isinstance(report_path, Path):
        report_paths = [report_path]

    # 自动发现 reports/selfcheck/、reports/ux/ 等子目录下的最新检查报告
    report_dirs = [
        PROJECT_ROOT / "reports",
        PROJECT_ROOT / "reports" / "selfcheck",
        PROJECT_ROOT / "reports" / "ux",
    ]
    latest = _find_latest_report(report_dirs)

    if report_paths:
        print(f"[INFO] 基于传入报告迭代：{[p.name for p in report_paths]}")
        # 同时把目录中最新的报告也纳入，避免遗漏 UX 等并发生成的报告
        if latest is not None and latest[0] not in report_paths:
            report_paths.append(latest[0])
            print(f"[INFO] 同时纳入最新检查报告：{latest[0].name}")
    elif latest is not None:
        report_paths = [latest[0]]
        print(f"[INFO] 基于最新检查报告迭代：{latest[0].name}")
    else:
        print("[WARN] 未找到可用的检查报告")

    parsed: Dict[str, List[str]] = {"issues": [], "suggestions": [], "critical": [], "important": [], "all": []}
    for rp in report_paths:
        if rp.exists():
            p = parse_report(rp)
            for key in parsed:
                parsed[key].extend(p.get(key, []))

    matched_names = _match_rules(rules, parsed["all"])
    print(f"[INFO] 匹配到的规则: {matched_names}")

    results = []
    restart_needed = False
    backend_was_restarted = False
    pending_restart_records: List[Tuple[Rule, Dict]] = []

    # 先处理 backend_restart
    backend_rule = next((r for r in rules if r.name == "backend_restart"), None)
    if backend_rule:
        detected, desc = backend_rule.detect()
        if detected:
            print(f"[AUTO] {backend_rule.name}: {desc}")
            ok, apply_msg = backend_rule.apply()
            vok, vmsg = backend_rule.verify()
            success = ok and vok
            results.append({
                "rule": backend_rule.name,
                "risk": backend_rule.risk,
                "detected": True,
                "applied": ok,
                "apply_msg": apply_msg,
                "verified": vok,
                "verify_msg": vmsg,
                "rolled_back": False,
                "success": success,
            })
            if success:
                backend_was_restarted = True
                restart_needed = False
        else:
            results.append({
                "rule": backend_rule.name,
                "risk": backend_rule.risk,
                "detected": False,
                "description": desc,
                "success": None,
            })

    # 处理其他规则
    for rule in rules:
        if rule.name == "backend_restart":
            continue

        detected, desc = rule.detect()
        record = {
            "rule": rule.name,
            "risk": rule.risk,
            "matched": rule.name in matched_names,
            "detected": detected,
            "detect_msg": desc,
        }

        if not detected:
            record["success"] = None
            results.append(record)
            continue

        if rule.risk == "high":
            record["action"] = "skipped_high_risk"
            record["reason"] = "高风险规则不自动执行，已加入待办"
            record["success"] = False
            results.append(record)
            continue

        print(f"[AUTO] {rule.name}: {desc}")
        ok, apply_msg = rule.apply()
        record["applied"] = ok
        record["apply_msg"] = apply_msg

        if not ok:
            record["success"] = False
            results.append(record)
            continue

        if rule.requires_restart:
            # 延迟到重启后再做运行时验证
            pending_restart_records.append((rule, record))
            restart_needed = True
            record["verified"] = None
            record["verify_msg"] = "等待后端重启后验证"
            record["success"] = None
            results.append(record)
            continue

        # 不需要重启的规则直接验证
        vok, vmsg = rule.verify()
        record["verified"] = vok
        record["verify_msg"] = vmsg

        if not vok:
            rbok, rbmsg = rule.rollback()
            record["rolled_back"] = rbok
            record["rollback_msg"] = rbmsg
            record["success"] = False
        else:
            record["rolled_back"] = False
            record["success"] = True

        results.append(record)

    # 统一重启后端（如果有代码变更需要重启且尚未重启）
    if restart_needed and not backend_was_restarted:
        print("[INFO] 有代码变更需要重启后端，正在统一重启...")
        rok, rmsg = _restart_backend()
        results.append({
            "rule": "_unified_restart",
            "risk": "medium",
            "detected": True,
            "applied": rok,
            "apply_msg": rmsg,
            "verified": rok,
            "verify_msg": rmsg,
            "rolled_back": False,
            "success": rok,
        })
        backend_was_restarted = rok

    # 对需要重启的规则做运行时验证
    if backend_was_restarted:
        for rule, record in pending_restart_records:
            vok, vmsg = rule.verify()
            record["verified"] = vok
            record["verify_msg"] = vmsg
            if not vok:
                rbok, rbmsg = rule.rollback()
                record["rolled_back"] = rbok
                record["rollback_msg"] = rbmsg
                record["success"] = False
                # 回滚后需要再次重启以恢复旧代码
                print(f"[WARN] {rule.name} 运行时验证失败，已回滚并准备再次重启")
                rok2, rmsg2 = _restart_backend()
                if not rok2:
                    print(f"[WARN] 回滚后重启失败: {rmsg2}")
            else:
                record["rolled_back"] = False
                record["success"] = True

    # 冒烟测试
    smoke_ok, smoke_msg = api_smoke_tests()
    if not smoke_ok:
        print(f"[WARN] 冒烟测试未通过: {smoke_msg}")

    # 未匹配问题 -> LLM 草案 / 待办
    unmatched = [issue for issue in parsed["all"] if not any(rule.matches(issue) for rule in rules)]
    llm_draft = _generate_llm_draft(unmatched) if unmatched else None

    # 生成迭代报告
    lines = [
        f"=== 自主迭代报告 ===",
        f"时间：{now.isoformat()}",
        f"基于报告：{', '.join(p.name for p in report_paths) if report_paths else '无'}",
        "",
        "## 执行结果",
        "",
    ]
    applied_rules = [r for r in results if r.get("success")]
    failed_rules = [r for r in results if r.get("detected") and r.get("success") is False and not r.get("action")]
    skipped_rules = [r for r in results if r.get("action") == "skipped_high_risk"]

    lines.append(f"- 自动修复成功：{len(applied_rules)} 条")
    lines.append(f"- 自动修复失败/回滚：{len(failed_rules)} 条")
    lines.append(f"- 高风险跳过：{len(skipped_rules)} 条")
    lines.append(f"- 冒烟测试：{'通过' if smoke_ok else '未通过'} ({smoke_msg})")
    lines.append("")

    if applied_rules:
        lines.append("### 已应用")
        for r in applied_rules:
            lines.append(f"- **{r['rule']}** ({r.get('risk', '-')})：{r.get('apply_msg', '')} | 验证：{r.get('verify_msg', '')}")
        lines.append("")

    if failed_rules:
        lines.append("### 失败/回滚")
        for r in failed_rules:
            lines.append(f"- **{r['rule']}**：{r.get('apply_msg', '')} | 验证：{r.get('verify_msg', '')} | 回滚：{r.get('rollback_msg', '')}")
        lines.append("")

    if skipped_rules:
        lines.append("### 高风险待人工确认")
        for r in skipped_rules:
            lines.append(f"- **{r['rule']}**：{r.get('detect_msg', '')}")
        lines.append("")

    if unmatched:
        lines.append("## 未覆盖问题")
        for issue in unmatched[:20]:
            lines.append(f"- {issue}")
        lines.append("")
        if llm_draft:
            lines.append("## LLM 修复草案")
            lines.append(llm_draft)
            lines.append("")
        else:
            lines.append("> LLM API Key 未配置，未生成自动草案。请人工 review 上述问题。")
            lines.append("")

    iteration_report_path.parent.mkdir(parents=True, exist_ok=True)
    iteration_report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[INFO] 迭代报告已保存: {iteration_report_path}")
    return iteration_report_path


if __name__ == "__main__":
    latest = _find_latest_report([
        PROJECT_ROOT / "reports",
        PROJECT_ROOT / "reports" / "selfcheck",
    ])
    run_iteration(latest[0] if latest else None)
